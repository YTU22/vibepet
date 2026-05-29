import time
import logging
from collections import namedtuple
import psutil
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("vibe_pet")

# 自定义网速数据结构，模拟 psutil.net_io_counters() 返回的命名元组
NetIO = namedtuple('NetIO', ['bytes_recv', 'bytes_sent'])


class SystemMonitorThread(QThread):
    """ 后台系统资源监控线程，每 N 秒采样一次，通过信号发送数据 """
    
    data_ready = pyqtSignal(dict)
    
    def __init__(self, interval=2):
        super().__init__()
        self.interval = interval
        self.running = True
        
        # 初始化 CPU 占用率基准（非阻塞采样）
        psutil.cpu_percent(interval=None)
        
        # 初始化网络计数器
        self.last_net = self._get_physical_net_io()
        self.last_net_time = time.time()
        
        # 初始化磁盘 IO 计数器
        self.last_disk = psutil.disk_io_counters()
        
        # GPU 支持检测
        self._gpu_available = False
        self._try_init_gpu()

    def _is_physical_interface(self, name):
        """ 过滤回环、虚拟、容器及代理/VPN 网卡，识别真实物理网卡 """
        name_lower = name.lower()
        ignore_keywords = [
            'loopback', 'pseudo', 'lo',
            'vmware', 'virtualbox', 'vbox', 'wsl', 'vethernet', 'hyper-v',
            'docker', 'sandbox',
            'mihomo', 'clash', 'sing-box', 'tun', 'tap', 'zerotier', 'tailscale', 'wireguard', 'openvpn',
            'vpn', 'forticlient', 'cisco', 'anyconnect', 'hamachi',
            'tunnel', 'teredo', 'isatap'
        ]
        for kw in ignore_keywords:
            if kw in name_lower:
                return False
        # 排除 Windows 临时/内部网络适配器（如 Wi-Fi Direct 虚拟适配器）
        if '*' in name:
            return False
        return True

    def _get_physical_net_io(self):
        """ 统计并求和所有活跃的真实物理网卡流量，并提供回退机制 """
        try:
            pernic = psutil.net_io_counters(pernic=True)
            recv_sum = 0
            sent_sum = 0
            has_physical = False
            for name, counters in pernic.items():
                if self._is_physical_interface(name):
                    recv_sum += counters.bytes_recv
                    sent_sum += counters.bytes_sent
                    has_physical = True
            
            if has_physical:
                return NetIO(bytes_recv=recv_sum, bytes_sent=sent_sum)
        except Exception as e:
            logger.error(f"Failed to sum physical interface counters: {e}")
            
        # 鲁棒回退：若过滤计算失败或未找到物理网卡，则使用系统全局统计
        try:
            tot = psutil.net_io_counters(pernic=False)
            return NetIO(bytes_recv=tot.bytes_recv, bytes_sent=tot.bytes_sent)
        except Exception as e:
            logger.error(f"Failed to fetch total net io counters fallback: {e}")
            return NetIO(bytes_recv=0, bytes_sent=0)
    
    def _try_init_gpu(self):
        """ 尝试以绿色零依赖方式（ctypes 加载 NVML DLL 或 win32pdh）初始化 GPU 监控 """
        # 1. 尝试加载 Nvidia NVML DLL
        import ctypes
        import os
        
        paths = [
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32\\nvml.dll"),
            "C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvml.dll"
        ]
        
        self._nvml_lib = None
        for path in paths:
            if os.path.exists(path):
                try:
                    self._nvml_lib = ctypes.CDLL(path)
                    break
                except Exception:
                    pass
                    
        if self._nvml_lib:
            try:
                # 初始化 NVML
                if self._nvml_lib.nvmlInit() == 0:
                    self._gpu_device = ctypes.c_void_p()
                    if self._nvml_lib.nvmlDeviceGetHandleByIndex(0, ctypes.byref(self._gpu_device)) == 0:
                        self._gpu_available = True
                        logger.info("NVIDIA GPU monitoring enabled via direct NVML loading (zero-dependency).")
                        return
                    else:
                        self._nvml_lib.nvmlShutdown()
            except Exception as e:
                logger.debug(f"NVML init failed: {e}")
                
        # 2. 如果无 Nvidia 卡或加载失败，初始化 win32pdh 作为 Fallback (支持 AMD/Intel/Nvidia)
        try:
            import win32pdh
            self._pdh_query = win32pdh.OpenQuery()
            self._pdh_counter = win32pdh.AddCounter(self._pdh_query, "\\GPU Engine(*)\\Utilization Percentage")
            win32pdh.CollectQueryData(self._pdh_query)
            logger.info("Universal GPU monitoring enabled via Windows Performance Counters (win32pdh).")
        except Exception as e:
            logger.error(f"Failed to initialize universal GPU performance counters: {e}")
            self._pdh_query = None
            self._pdh_counter = None
    
    def stop(self):
        self.running = False
        
        # 释放 win32pdh 查询
        if hasattr(self, '_pdh_query') and self._pdh_query:
            try:
                import win32pdh
                win32pdh.CloseQuery(self._pdh_query)
            except Exception:
                pass
            self._pdh_query = None
            self._pdh_counter = None
            
        # 释放 NVML
        if hasattr(self, '_gpu_available') and self._gpu_available and self._nvml_lib:
            try:
                self._nvml_lib.nvmlShutdown()
            except Exception:
                pass
            self._gpu_available = False
            self._nvml_lib = None
            
        self.wait(1000)
    
    def run(self):
        logger.info(f"SystemMonitorThread started, interval={self.interval}s")
        
        while self.running:
            loop_start = time.time()
            data = {}
            
            # 1. CPU：非阻塞采样，计算自上次采样以来的平均占用
            try:
                data['cpu'] = psutil.cpu_percent(interval=None)
            except Exception as e:
                logger.error(f"CPU sample failed: {e}")
                data['cpu'] = 0.0
            
            # 2. 内存：静态值，直接读取
            try:
                mem = psutil.virtual_memory()
                data['memory'] = mem.percent
                data['memory_used'] = mem.used / (1024 ** 3)
                data['memory_total'] = mem.total / (1024 ** 3)
            except Exception as e:
                logger.error(f"Memory sample failed: {e}")
                data['memory'] = 0.0
            
            # 3. 磁盘 IO：计算读写速率（KB/s），而非空间占用
            try:
                disk_io = psutil.disk_io_counters()
                if disk_io and self.last_disk:
                    read_diff = disk_io.read_bytes - self.last_disk.read_bytes
                    write_diff = disk_io.write_bytes - self.last_disk.write_bytes
                    
                    # 处理计数器重置
                    if read_diff < 0:
                        read_diff = 0
                    if write_diff < 0:
                        write_diff = 0
                    
                    data['disk_read'] = read_diff / 1024.0 / self.interval  # KB/s
                    data['disk_write'] = write_diff / 1024.0 / self.interval  # KB/s
                    data['disk_total'] = (read_diff + write_diff) / 1024.0 / self.interval
                else:
                    data['disk_read'] = 0.0
                    data['disk_write'] = 0.0
                    data['disk_total'] = 0.0
                
                self.last_disk = disk_io
            except Exception as e:
                logger.error(f"Disk IO sample failed: {e}")
                data['disk_read'] = 0.0
                data['disk_write'] = 0.0
                data['disk_total'] = 0.0
            
            # 4. 网速：差值法计算发送/接收速率
            try:
                curr_net = self._get_physical_net_io()
                curr_time = time.time()
                delta = curr_time - self.last_net_time
                
                if delta > 0 and self.last_net:
                    sent_diff = curr_net.bytes_sent - self.last_net.bytes_sent
                    recv_diff = curr_net.bytes_recv - self.last_net.bytes_recv
                    
                    # 处理计数器重置
                    if sent_diff < 0:
                        sent_diff = 0
                    if recv_diff < 0:
                        recv_diff = 0
                    
                    data['net_upload'] = sent_diff / 1024.0 / delta  # KB/s
                    data['net_download'] = recv_diff / 1024.0 / delta  # KB/s
                else:
                    data['net_upload'] = 0.0
                    data['net_download'] = 0.0
                
                self.last_net = curr_net
                self.last_net_time = curr_time
            except Exception as e:
                logger.error(f"Network sample failed: {e}")
                data['net_upload'] = 0.0
                data['net_download'] = 0.0
            
            # 5. GPU（绿色读取，无 GPUtil 依赖）
            gpu_val = 0.0
            gpu_mem_val = 0.0
            
            if self._gpu_available and self._nvml_lib and self._gpu_device:
                try:
                    import ctypes
                    class nvmlUtilization_t(ctypes.Structure):
                        _fields_ = [
                            ('gpu', ctypes.c_uint),
                            ('memory', ctypes.c_uint)
                        ]
                    rates = nvmlUtilization_t()
                    if self._nvml_lib.nvmlDeviceGetUtilizationRates(self._gpu_device, ctypes.byref(rates)) == 0:
                        gpu_val = float(rates.gpu)
                        gpu_mem_val = float(rates.memory)
                except Exception as e:
                    logger.debug(f"NVML GPU query failed: {e}")
            elif self._pdh_query and self._pdh_counter:
                try:
                    import win32pdh
                    win32pdh.CollectQueryData(self._pdh_query)
                    items = win32pdh.GetFormattedCounterArray(self._pdh_counter, win32pdh.PDH_FMT_DOUBLE)
                    total_3d = 0.0
                    for name, val in items.items():
                        if "engtype_3d" in name.lower():
                            total_3d += val
                    gpu_val = min(100.0, total_3d)
                except Exception as e:
                    logger.debug(f"PDH GPU query failed: {e}")
            
            data['gpu'] = gpu_val
            data['gpu_memory'] = gpu_mem_val
            
            # 发射数据
            self.data_ready.emit(data)
            
            # 计算剩余睡眠时间（扣除 CPU 采样 0.5 秒）
            elapsed = time.time() - loop_start
            sleep_time = max(0.1, self.interval - elapsed)
            time.sleep(sleep_time)
        
        logger.info("SystemMonitorThread stopped.")

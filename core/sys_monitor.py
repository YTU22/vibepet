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
        """ 尝试初始化 GPU 监控 """
        try:
            import gputil
            gpus = gputil.getGPUs()
            if gpus:
                self._gpu_available = True
                logger.info(f"GPU monitoring enabled (GPUtil), found {len(gpus)} GPU(s)")
        except ImportError:
            logger.info("GPUtil not installed, GPU monitoring disabled")
        except Exception as e:
            logger.debug(f"GPU init failed: {e}")
    
    def stop(self):
        self.running = False
        self.wait(1000)
    
    def run(self):
        logger.info(f"SystemMonitorThread started, interval={self.interval}s")
        
        while self.running:
            loop_start = time.time()
            data = {}
            
            # 1. CPU：阻塞采样 0.5 秒，得到真实平均占用
            try:
                data['cpu'] = psutil.cpu_percent(interval=0.5)
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
            
            # 5. GPU（可选）：仅当 gputil 安装时读取
            if self._gpu_available:
                try:
                    import gputil
                    gpus = gputil.getGPUs()
                    if gpus:
                        gpu = gpus[0]
                        data['gpu'] = gpu.load * 100
                        data['gpu_memory'] = gpu.memoryUtil * 100
                    else:
                        data['gpu'] = 0.0
                        data['gpu_memory'] = 0.0
                except Exception as e:
                    logger.debug(f"GPU sample failed: {e}")
                    data['gpu'] = 0.0
                    data['gpu_memory'] = 0.0
            else:
                data['gpu'] = 0.0
                data['gpu_memory'] = 0.0
            
            # 发射数据
            self.data_ready.emit(data)
            
            # 计算剩余睡眠时间（扣除 CPU 采样 0.5 秒）
            elapsed = time.time() - loop_start
            sleep_time = max(0.1, self.interval - elapsed)
            time.sleep(sleep_time)
        
        logger.info("SystemMonitorThread stopped.")

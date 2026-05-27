import os
import sys
import winshell
from win32com.client import Dispatch

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Resolve path relative to the directory of main.py which is parent of utils/
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        
    return os.path.join(base_path, relative_path)

def get_app_dir():
    """ Get the directory where application writable data should be stored """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # Resolve path relative to the directory of main.py which is parent of utils/
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def normalize_process_name(process_name):
    """ Standardize process name by converting to lowercase and stripping .exe suffix """
    if not process_name:
        return "unknown"
    
    # Strip whitespace, lowercase, and remove .exe
    name = process_name.strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
        
    # Standard software mapping/aliasing
    aliases = {
        # Browsers
        "chrome": "browser",
        "msedge": "browser",
        "firefox": "browser",
        "safari": "browser",
        "opera": "browser",
        "iexplore": "browser",
        
        # IDEs / Development
        "pycharm64": "pycharm",
        "idea64": "intellij idea",
        "clion64": "clion",
        "webstorm64": "webstorm",
        "code": "vscode",
        "devenv": "visual studio",
        
        # Office / Writing
        "winword": "word",
        "excel": "excel",
        "powerpnt": "powerpoint",
        
        # Game launchers / Games
        "genshinimpact": "genshin impact",
        "genshin": "genshin impact",
        "league of legends": "lol",
        "leagueoflegends": "lol",
        "valorant-win64-shipping": "valorant",
    }
    
    return aliases.get(name, name)


def create_desktop_shortcut(target_path, shortcut_name="VibePet", icon_path=None):
    """ 在桌面创建快捷方式 """
    try:
        desktop = winshell.desktop()
        shortcut_path = os.path.join(desktop, f"{shortcut_name}.lnk")
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = target_path
        shortcut.WorkingDirectory = os.path.dirname(target_path)
        if icon_path and os.path.exists(icon_path):
            shortcut.IconLocation = icon_path
        else:
            shortcut.IconLocation = target_path
        shortcut.save()
        return True
    except Exception as e:
        print(f"Failed to create desktop shortcut: {e}")
        return False


def set_auto_start(enabled, app_name="VibePet"):
    """ 设置/取消开机自启动（写入注册表 Run 键） """
    import winreg
    try:
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        if enabled:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Failed to set auto-start: {e}")
        return False


def is_auto_start_enabled(app_name="VibePet"):
    """ 检查是否已设置开机自启动 """
    import winreg
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

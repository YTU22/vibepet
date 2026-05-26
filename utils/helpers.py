import os
import sys

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

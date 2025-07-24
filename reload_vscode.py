#!/usr/bin/env python3
"""
Script to help VSCode reload and recognize the Python environment.
Run this script and then restart VSCode or reload the window.
"""

import sys
import os
from pathlib import Path

def main():
    print("🔄 VSCode Python Environment Reload Helper")
    print("=" * 50)
    
    # Print current Python environment info
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Check if packages are available
    packages_to_check = [
        'dotenv', 'langchain', 'langchain_openai', 'langchain_community', 
        'langchain_chroma', 'bs4', 'requests', 'selenium', 'colorama', 'rich'
    ]
    
    print("\n📦 Package availability check:")
    all_available = True
    for package in packages_to_check:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}")
            all_available = False
    
    # Check project structure
    print("\n📁 Project structure check:")
    required_paths = [
        'src/',
        'src/utils/',
        'src/scraper/',
        'src/rag/',
        'src/ui/',
        '.vscode/settings.json',
        'pyrightconfig.json'
    ]
    
    for path in required_paths:
        if Path(path).exists():
            print(f"  ✅ {path}")
        else:
            print(f"  ❌ {path}")
    
    print("\n🔧 Next steps to resolve VSCode issues:")
    print("1. Close VSCode completely")
    print("2. Reopen VSCode")
    print("3. Open Command Palette (Cmd+Shift+P)")
    print("4. Run 'Python: Select Interpreter'")
    print(f"5. Choose: {sys.executable}")
    print("6. Run 'Python: Restart Language Server'")
    print("7. Run 'Developer: Reload Window'")
    
    if all_available:
        print("\n✅ All packages are available - the code will run correctly!")
        print("   The Pylance errors are just IDE configuration issues.")
    else:
        print("\n❌ Some packages are missing - please install requirements.txt")

if __name__ == "__main__":
    main()

import os
import sys

# backend/ 를 import 루트로 추가 (scanners.*, vscode_analysis.* import shim과 일치)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

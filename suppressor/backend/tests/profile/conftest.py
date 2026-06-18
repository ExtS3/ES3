import os
import sys

# backend/ 를 import 루트로 추가 (profile.* import 가 stdlib profile 보다 우선)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

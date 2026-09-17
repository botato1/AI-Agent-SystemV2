import os
import sys

# 다른 stt 스크립트들과 같은 관례: backend/modules를 sys.path에 넣어서
# `import stt.services...`가 어디서 pytest를 실행하든 되게 한다.
_HERE = os.path.dirname(os.path.abspath(__file__))          # .../backend/modules/stt/tests
_BACKEND_MODULES = os.path.dirname(os.path.dirname(_HERE))  # .../backend/modules
sys.path.insert(0, _BACKEND_MODULES)

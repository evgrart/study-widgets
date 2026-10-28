"""Keep user state and authentication outside the source checkout."""
import os
from pathlib import Path
CODE_ROOT=Path(__file__).resolve().parent
_local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))
ROOT=Path(os.environ.get('SCHEDULE_WIDGET_DATA_DIR',str(_local/'StudyWidgets'/'Schedule'))).expanduser().resolve()
ROOT.mkdir(parents=True,exist_ok=True)

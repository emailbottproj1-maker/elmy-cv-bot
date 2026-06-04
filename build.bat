@echo off
REM ============================================================
REM  Build ElmyCVBot.exe  (standalone Windows desktop app)
REM  Requires: pip install pyinstaller
REM ============================================================
echo Installing/Updating dependencies...
python -m pip install -r requirements.txt

echo.
echo Building executable...
pyinstaller --noconfirm --onefile --windowed ^
  --name "ElmyCVBot" ^
  --icon "assets/icon.ico" ^
  --add-data "data/cover_letter_ar.txt;data" ^
  --add-data "data/cover_letter_en.txt;data" ^
  --hidden-import "PIL._tkinter_finder" ^
  main.py

echo.
echo ============================================================
echo Done. The executable is in:  dist\ElmyCVBot.exe
echo Ship the WHOLE dist\ folder OR just ElmyCVBot.exe (onefile).
echo ============================================================
pause

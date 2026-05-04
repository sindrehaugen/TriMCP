Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "c:\Users\SindreLøvlieHaugen\Documents\systemer\TriMCP\TriMCP-1\.venv\Scripts\pythonw.exe" & Chr(34) & " " & chr(34) & "c:\Users\SindreLøvlieHaugen\Documents\systemer\TriMCP\TriMCP-1\start_worker.py" & Chr(34), 0
Set WshShell = Nothing

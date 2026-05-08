Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strAppPath = "c:\Users\SindreLøvlieHaugen\Documents\systemer\TriMCP\TriMCP-1"
strGoLauncher = strAppPath & "\go\trimcp-launch.exe"

If fso.FileExists(strGoLauncher) Then
    ' Use the robust Go-based launcher for v1.0
    WshShell.Run chr(34) & strGoLauncher & Chr(34), 0
Else
    ' Fallback to pythonw if launcher is missing
    WshShell.Run chr(34) & strAppPath & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & chr(34) & strAppPath & "\start_worker.py" & Chr(34), 0
End If

Set WshShell = Nothing
Set fso = Nothing

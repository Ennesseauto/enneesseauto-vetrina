' Esegue l'aggiornamento annunci + cartella Drive in background senza aprire finestre nere sul PC del concessionario.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
cartellaStrumenti = fso.GetParentFolderName(WScript.ScriptFullName)
cartellaRepost = fso.GetParentFolderName(cartellaStrumenti)
fileLog = cartellaRepost & "\dati\ultimo_aggiornamento.log"

comando = "cmd /c cd /d """ & cartellaRepost & """ && set PYTHONIOENCODING=utf-8 && (python ""strumenti\aggiorna_annunci.py"" > """ & fileLog & """ 2>&1 || py -3 ""strumenti\aggiorna_annunci.py"" > """ & fileLog & """ 2>&1)"
shell.Run comando, 0, True

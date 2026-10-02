#Requires AutoHotkey v2.0
; Text Maths hotkeys: select some text, press a hotkey, and the answers
; replace the selection. Keep this file next to the .pyw files, or set
; TextMathsDir to the folder they are in.

TextMathsDir := A_ScriptDir

TextMaths(script) {
    ; Wait for the hotkey's keys to be let go, so Ctrl+C isn't sent as Ctrl+Alt+C.
    KeyWait "Alt"
    KeyWait "Shift"
    KeyWait "LWin"
    KeyWait "RWin"

    ; Empty the clipboard first and wait for the copy to land. Without this,
    ; Python can read the *previous* clipboard and paste that over your text.
    A_Clipboard := ""
    Send "^c"
    if !ClipWait(1)
        return                          ; nothing was selected

    ; Opens with whatever runs .pyw files on this PC (pythonw / the py launcher).
    ; To pick a Python yourself:  RunWait 'pythonw.exe "' TextMathsDir '\' script '"'
    RunWait '"' TextMathsDir '\' script '"'
}

^!1::TextMaths("Text Maths - Pure Maths.pyw")
^!2::TextMaths("Text Maths - Pure Maths and Units.pyw")
^!3::TextMaths("Text Maths - Variables.pyw")
^!4::TextMaths("Text Maths - Variables with Substitution.pyw")

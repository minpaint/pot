Attribute VB_Name = "Module1"
Sub PrintSheetsBasedOnData()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("Ѕаза")
    Dim i As Long
    Dim shouldPrintFullSet As Boolean

    ' ѕеребор строк в столбце A
    For i = 1 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If ws.Cells(i, 1).value = "a" Then
            ' ќпределение, нужно ли печатать полный набор листов
            shouldPrintFullSet = Not IsEmpty(ws.Cells(i, 9).value)
            Exit For
        End If
    Next i

    ' ѕечать листов
    Dim sheet As Worksheet
    For Each sheet In ThisWorkbook.Sheets
        On Error GoTo ErrorHandler
        If shouldPrintFullSet Then
            ' ѕечать всех листов, где в названии есть точка, кроме "4.1 ƒневник (подготовка)"
            If InStr(sheet.Name, ".") > 0 And sheet.Name <> "4.1 ƒневник (подготовка)" Then
                sheet.PrintOut
            End If
        Else
            ' ѕечать всех листов, где в названии есть точка, кроме "4. ƒневник (переподготовка)"
            If InStr(sheet.Name, ".") > 0 And sheet.Name <> "4. ƒневник (переподготовка)" Then
                sheet.PrintOut
            End If
        End If
        On Error GoTo 0
    Next sheet
    Exit Sub

ErrorHandler:
    MsgBox "ќшибка при печати листа '" & sheet.Name & "': " & Err.Description
    Resume Next
End Sub


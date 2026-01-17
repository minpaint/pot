Attribute VB_Name = "Module2"
Function ReplaceMonthNumberWithBelarusianName(dateStr As String) As String
    Dim monthNames As Object
    Set monthNames = CreateObject("Scripting.Dictionary")
    
    ' Сопоставление числовых обозначений месяцев с белорусскими названиями в родительном падеже
    monthNames.Add "01", "студзеня"
    monthNames.Add "02", "лютага"
    monthNames.Add "03", "сакавіка"
    monthNames.Add "04", "красавіка"
    monthNames.Add "05", "траўня"
    monthNames.Add "06", "чэрвеня"
    monthNames.Add "07", "ліпеня"
    monthNames.Add "08", "жніўня"
    monthNames.Add "09", "верасня"
    monthNames.Add "10", "кастрычніка"
    monthNames.Add "11", "лістапада"
    monthNames.Add "12", "снежня"
    
    ' Разделение даты на компоненты
    Dim dateParts As Variant
    dateParts = Split(dateStr, ".")
    
    ' Удаление ведущего нуля из дня
    Dim dayPart As String
    dayPart = Trim(Str(Int(dateParts(0))))  ' Преобразование в число и обратно в строку для удаления нуля

    ' Замена месяца и формирование новой даты
    If UBound(dateParts) = 2 Then
        Dim monthName As String
        monthName = monthNames(dateParts(1))
        ReplaceMonthNumberWithBelarusianName = dayPart & " " & monthName & " " & dateParts(2) & " г."
    Else
        ReplaceMonthNumberWithBelarusianName = dateStr
    End If
End Function

Sub ProcessDatesAndReplaceMonths()
    Dim xlSheet As Worksheet
    Dim i As Long
    Dim originalDateR As String
    Dim originalDateT As String
    Dim processedDateR As String
    Dim processedDateT As String

    ' Установка листа Excel
    Set xlSheet = ThisWorkbook.Sheets("База")

    ' Перебор строк
    For i = 7 To xlSheet.Cells(xlSheet.Rows.Count, 1).End(-4162).Row
        originalDateR = xlSheet.Cells(i, 18).value ' Чтение даты из столбца R
        originalDateT = xlSheet.Cells(i, 20).value ' Чтение даты из столбца T

        processedDateR = ReplaceMonthNumberWithBelarusianName(originalDateR) ' Обработка даты R
        processedDateT = ReplaceMonthNumberWithBelarusianName(originalDateT) ' Обработка даты T

        xlSheet.Cells(i, 19).value = processedDateR ' Запись обработанной даты в столбец S
        xlSheet.Cells(i, 21).value = processedDateT ' Запись обработанной даты в столбец U
    Next i
End Sub

Sub FillWordDocumentAndSaveAsNewFile()
    Dim wdApp As Object
    Dim wdDoc As Object
    Dim xlSheet As Worksheet
    Dim i As Long
    Dim j As Integer
    Dim shpName As String
    Dim data As String
    Dim wordFilePath As String
    Dim newFileName As String

    ' Получение пути к папке, где находится файл Excel
    Dim excelFilePath As String
    excelFilePath = ThisWorkbook.Path

    ' Установка пути к файлу Word
    wordFilePath = excelFilePath & "\макет.docx"

    ' Подключение к Word
    Set wdApp = CreateObject("Word.Application")
    wdApp.Visible = True ' Для отладки
    Set wdDoc = wdApp.Documents.Open(wordFilePath)

    ' Установка листа Excel
    Set xlSheet = ThisWorkbook.Sheets("База")

    ' Перебор строк, начиная с 7-й строки
    For i = 7 To xlSheet.Cells(xlSheet.Rows.Count, 1).End(-4162).Row
        If xlSheet.Cells(i, 1).value = "a" Then
            ' Преобразование дат в столбцах R и T
            xlSheet.Cells(i, 19).value = ReplaceMonthNumberWithBelarusianName(xlSheet.Cells(i, 18).value)
            xlSheet.Cells(i, 21).value = ReplaceMonthNumberWithBelarusianName(xlSheet.Cells(i, 20).value)

            ' Заполнение текстовых полей в Word
            For j = 11 To 21 ' Столбцы K-U
                shpName = CStr(xlSheet.Cells(6, j).value)
                data = CStr(xlSheet.Cells(i, j).Text)
                For Each shp In wdDoc.Shapes
                    If CStr(shp.Name) = shpName Then
                        shp.TextFrame.TextRange.Text = data
                    End If
                Next shp
            Next j

            ' Формирование нового имени файла
            newFileName = xlSheet.Cells(i, 14).Text & " " & xlSheet.Cells(i, 15).Text & ".docx"
            ' Сохранение документа с новым именем
            wdDoc.SaveAs2 (excelFilePath & "\" & newFileName)
        End If
    Next i

    ' Закрытие исходного документа Word без сохранения изменений
    wdDoc.Close SaveChanges:=False
    Set wdDoc = Nothing
    wdApp.Quit
    Set wdApp = Nothing
End Sub

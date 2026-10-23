@echo off
setlocal
cd /d "%~dp0.."
echo OFI - Transformacao e compilacao de surveys
echo.
echo 1 - Preparar arquivos CSV para transcricao/revisao
echo 2 - Validar CSVs preenchidos (sem alterar Excel)
echo 3 - Simular aplicacao (validar sem alterar Excel)
echo 4 - Aplicar dados validados no Excel (cria backup)
echo.
choice /c 1234 /n /m "Escolha uma opcao: "
if errorlevel 4 goto aplicar
if errorlevel 3 goto simular
if errorlevel 2 goto validar
if errorlevel 1 goto preparar

:preparar
conda run -n ofi python scripts\processar_survey_vessels.py --preparar
goto fim
:validar
conda run -n ofi python scripts\processar_survey_vessels.py --validar
goto fim
:simular
conda run -n ofi python scripts\processar_survey_vessels.py --aplicar --simular
goto fim
:aplicar
echo.
echo ATENCAO: esta opcao altera planilhas. Backups serao criados automaticamente.
choice /c SN /m "Continuar"
if errorlevel 2 goto fim
conda run -n ofi python scripts\processar_survey_vessels.py --aplicar
:fim
echo.
pause

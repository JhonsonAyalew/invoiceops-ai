@echo off
setlocal EnableDelayedExpansion
set "DEST=%LOCALAPPDATA%\InvoiceOps\paddle_models"
set "BASE=https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
if not exist "%DEST%" mkdir "%DEST%"
for %%M in (PP-OCRv6_medium_det PP-OCRv6_medium_rec) do (
  set "TAR=%DEST%\%%M_infer.tar"
  echo Downloading %%M ...
  curl.exe -L --retry 5 --retry-delay 2 --retry-all-errors -C - -o "!TAR!" "%BASE%/%%M_infer.tar" || goto :error
  if exist "%DEST%\%%M_infer" rmdir /s /q "%DEST%\%%M_infer"
  tar -xf "!TAR!" -C "%DEST%" || goto :error
  if exist "%DEST%\%%M" rmdir /s /q "%DEST%\%%M"
  move /y "%DEST%\%%M_infer" "%DEST%\%%M" >nul || goto :error
)
echo.
echo PP-OCRv6 Medium models ready in %DEST%
endlocal
exit /b 0
:error
echo.
echo Model download failed. Re-run this script; curl will resume partial downloads.
endlocal
exit /b 1

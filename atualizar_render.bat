@echo off
title Atualizar Controle Fiado no Render
cd /d "%USERPROFILE%\Desktop\Controle Fiado\controle_fiado"

echo.
echo ===========================================
echo   🚀 ATUALIZANDO PROJETO CONTROLE FIADO...
echo ===========================================
echo.

git add .
set /p msg="Digite uma mensagem para o commit: "
if "%msg%"=="" set msg=Atualizacao automatica

git commit -m "%msg%"
git push

echo.
echo ✅ Código enviado com sucesso!
echo 🔄 Render vai atualizar automaticamente em 1 a 2 minutos.
echo.
pause

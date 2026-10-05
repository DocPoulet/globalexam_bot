@echo off
echo Suppression de la session sauvegardee...

if exist data\session.json (
    del data\session.json
    echo Session supprimee.
) else (
    echo Aucune session trouvee.
)

pause

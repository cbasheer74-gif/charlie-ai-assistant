@echo off
cd /d "%~dp0Charlie-Ai assistant"
echo Staging and committing changes...
git add -A
git commit -m "feat(avatar): Blender-grade FACS lip-sync, acoustic emotion & voice profile integration" -m "- Fix female lip landmark positioning (0.598 seam) eliminating chin-mouth rendering artifact" -m "- Clamp male jaw drop to anatomical speech bounds (0.024 max) matching Blender FACS standards" -m "- Add cubic Hermite mucosal edge feathering and recessed shadowed tooth enamel shading" -m "- Optimize PhotoRealisticRig grid caching and polynomial decay (390+ FPS male, 100+ FPS female)" -m "- Wire real-time acoustic emotion detector and voice profile speaker recognition to HUD avatar" -m "- Add affirmative conversational micro-nod gesture on speech initiation"
git status
pause

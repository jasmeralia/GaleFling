; GalePost NSIS Installer Script

!include "MUI2.nsh"

Name "GalePost"
OutFile "GalePost-Setup-v0.2.36.exe"
InstallDir "$PROGRAMFILES\GalePost"
InstallDirRegKey HKLM "Software\GalePost" "InstallDir"
RequestExecutionLevel admin

; Modern UI settings
!define MUI_ABORTWARNING
!define MUI_ICON "..\resources\icon.ico"
!define MUI_UNICON "..\resources\icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\GalePost.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch GalePost"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE.md"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "GalePost (required)" SecMain
  SectionIn RO
  ExecWait "taskkill /IM GalePost.exe /T"
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
  File "..\dist\GalePost.exe"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start menu shortcut
  CreateDirectory "$SMPROGRAMS\GalePost"
  CreateShortCut "$SMPROGRAMS\GalePost\GalePost.lnk" "$INSTDIR\GalePost.exe"
  CreateShortCut "$SMPROGRAMS\GalePost\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Registry
  WriteRegStr HKLM "Software\GalePost" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\GalePost" "Version" "0.2.36"

  ; Add/Remove Programs entry
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "DisplayName" "GalePost"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "DisplayVersion" "0.2.36"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "Publisher" "GalePost"
SectionEnd

Section /o "Desktop Shortcut" SecDesktop
  CreateShortCut "$DESKTOP\GalePost.lnk" "$INSTDIR\GalePost.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\GalePost.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\GalePost\GalePost.lnk"
  Delete "$SMPROGRAMS\GalePost\Uninstall.lnk"
  RMDir "$SMPROGRAMS\GalePost"
  Delete "$DESKTOP\GalePost.lnk"

  DeleteRegKey HKLM "Software\GalePost"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost"
SectionEnd

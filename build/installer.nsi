; GaleFling NSIS Installer Script

!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "GaleFling"
OutFile "GaleFling-Setup-v0.2.55.exe"
InstallDir "$PROGRAMFILES\GaleFling"
InstallDirRegKey HKLM "Software\GaleFling" "InstallDir"
RequestExecutionLevel admin

; Modern UI settings
!define MUI_ABORTWARNING
!define MUI_ICON "..\resources\icon.ico"
!define MUI_UNICON "..\resources\icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\GaleFling.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch GaleFling"

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

Section "GaleFling (required)" SecMain
  SectionIn RO
  StrCpy $2 0
  kill_loop:
    ExecWait "taskkill /F /IM GaleFling.exe /T"
    Sleep 1000
    nsExec::ExecToStack 'cmd /C tasklist /FI "IMAGENAME eq GaleFling.exe" /NH | findstr /I "GaleFling.exe"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      IntOp $2 $2 + 1
      ${If} $2 >= 5
        MessageBox MB_ICONSTOP "GaleFling is still running. Please close the app and retry the installer."
        Abort
      ${Else}
        Sleep 1000
        Goto kill_loop
      ${EndIf}
    ${EndIf}
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
  File "..\dist\GaleFling.exe"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start menu shortcut
  CreateDirectory "$SMPROGRAMS\GaleFling"
  CreateShortCut "$SMPROGRAMS\GaleFling\GaleFling.lnk" "$INSTDIR\GaleFling.exe"
  CreateShortCut "$SMPROGRAMS\GaleFling\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Registry
  WriteRegStr HKLM "Software\GaleFling" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\GaleFling" "Version" "0.2.55"

  ; Add/Remove Programs entry
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GaleFling" \
    "DisplayName" "GaleFling"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GaleFling" \
    "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GaleFling" \
    "DisplayVersion" "0.2.55"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GaleFling" \
    "Publisher" "GaleFling"
SectionEnd

Section /o "Desktop Shortcut" SecDesktop
  CreateShortCut "$DESKTOP\GaleFling.lnk" "$INSTDIR\GaleFling.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\GaleFling.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\GaleFling\GaleFling.lnk"
  Delete "$SMPROGRAMS\GaleFling\Uninstall.lnk"
  RMDir "$SMPROGRAMS\GaleFling"
  Delete "$DESKTOP\GaleFling.lnk"

  DeleteRegKey HKLM "Software\GaleFling"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\GaleFling"
SectionEnd

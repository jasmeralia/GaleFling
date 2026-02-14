; GalePost NSIS Installer Script

!include "MUI2.nsh"

Name "GalePost"
OutFile "GalePost-Setup-v0.2.2.exe"
InstallDir "$PROGRAMFILES\GalePost"
InstallDirRegKey HKCU "Software\GalePost" "InstallDir"
RequestExecutionLevel user

; Modern UI settings
!define MUI_ABORTWARNING
!define MUI_ICON "..\resources\icon.ico"
!define MUI_UNICON "..\resources\icon.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File "..\dist\GalePost.exe"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start menu shortcut
  CreateDirectory "$SMPROGRAMS\GalePost"
  CreateShortCut "$SMPROGRAMS\GalePost\GalePost.lnk" "$INSTDIR\GalePost.exe"
  CreateShortCut "$SMPROGRAMS\GalePost\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\GalePost.lnk" "$INSTDIR\GalePost.exe"

  ; Registry
  WriteRegStr HKCU "Software\GalePost" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\GalePost" "Version" "0.2.2"

  ; Add/Remove Programs entry
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "DisplayName" "GalePost"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "DisplayVersion" "0.2.2"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost" \
    "Publisher" "GalePost"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\GalePost.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\GalePost\GalePost.lnk"
  Delete "$SMPROGRAMS\GalePost\Uninstall.lnk"
  RMDir "$SMPROGRAMS\GalePost"
  Delete "$DESKTOP\GalePost.lnk"

  DeleteRegKey HKCU "Software\GalePost"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalePost"
SectionEnd

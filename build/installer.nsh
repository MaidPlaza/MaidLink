!include "${BUILD_RESOURCES_DIR}\installer_ru.nsh"

!macro customWelcomePage
  !define MUI_PAGE_HEADER_TEXT "${MAIDLINK_LICENSE_TITLE}"
  !define MUI_PAGE_HEADER_SUBTEXT "${MAIDLINK_LICENSE_SUBTITLE}"
!macroend

!macro _maidlink_kill_processes
  nsExec::Exec `taskkill /F /IM llama-server.exe`
  nsExec::Exec `powershell -NoProfile -Command "Get-Process backend -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like '*\resources\backend\backend.exe' } | Stop-Process -Force"`
  Sleep 500
!macroend

!macro customInit
  !insertmacro _maidlink_kill_processes
!macroend

!macro customUnInit
  !insertmacro _maidlink_kill_processes
!macroend

!macro _maidlink_drop_installer_copy
  ${if} $installMode == "all"
    SetShellVarContext current
  ${endif}
  !ifdef APP_INSTALLER_STORE_FILE
    Delete "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
  !endif
  !ifdef APP_PACKAGE_NAME
    RMDir "$LOCALAPPDATA\${APP_PACKAGE_NAME}-updater"
  !endif
  RMDir /r "$LOCALAPPDATA\maidai-updater"
  ${if} $installMode == "all"
    SetShellVarContext all
  ${endif}
!macroend

!macro customInstall
  !insertmacro _maidlink_drop_installer_copy
!macroend

!macro customUnInstall
  ${IfNot} ${isUpdated}
    !insertmacro _maidlink_drop_installer_copy
  ${EndIf}
!macroend

!macro customRemoveFiles
  FindFirst $R0 $R1 "$INSTDIR\*.*"
  ${DoWhile} $R1 != ""
    ${If} $R1 != "."
    ${AndIf} $R1 != ".."
    ${AndIf} $R1 != "userdata"
      ${If} ${FileExists} "$INSTDIR\$R1\*.*"
        RMDir /r "$INSTDIR\$R1"
      ${Else}
        Delete "$INSTDIR\$R1"
      ${EndIf}
    ${EndIf}
    FindNext $R0 $R1
  ${Loop}
  FindClose $R0

  ${IfNot} ${isUpdated}
  ${AndIfNot} ${Silent}
  ${AndIf} ${FileExists} "$INSTDIR\userdata\*.*"
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Also delete downloaded models and character saves?$\r$\n$\r$\n$INSTDIR\userdata$\r$\n$\r$\nChoose No to keep them for a later reinstall." IDNO maidlink_keep_data
      RMDir /r "$INSTDIR\userdata"
      Delete "$LOCALAPPDATA\MaidLink\data_location.txt"
      RMDir "$LOCALAPPDATA\MaidLink"
    maidlink_keep_data:
  ${EndIf}

  RMDir "$INSTDIR"
!macroend

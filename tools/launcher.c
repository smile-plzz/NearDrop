#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR arguments,int show){
    static wchar_t folder[32768],python[32768],script[32768],command[32768];
    DWORD n=GetModuleFileNameW(NULL,folder,32768);
    if(!n||n>=32000){MessageBoxW(NULL,L"The application path is too long. Extract NearDrop to a shorter folder.",L"NearDrop",MB_ICONERROR);return 1;}
    wchar_t *slash=wcsrchr(folder,L'\\');if(!slash)return 1;*slash=0;
    if(wcslen(folder)>15000)return 1;
    swprintf(python,32768,L"%ls\\runtime\\python.exe",folder);
    swprintf(script,32768,L"%ls\\app\\server.py",folder);
    if(GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES||GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES){
        MessageBoxW(NULL,L"Please extract the entire NearDrop ZIP before launching. Keep the runtime and app folders next to NearDrop.exe.",L"NearDrop - Files missing",MB_OK|MB_ICONINFORMATION);return 1;
    }
    swprintf(command,32768,L"\"%ls\" \"%ls\"",python,script);
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);startup.lpTitle=L"NearDrop - Keep this window open while sharing";
    PROCESS_INFORMATION process={0};
    if(!CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NEW_CONSOLE,NULL,folder,&startup,&process)){
        MessageBoxW(NULL,L"NearDrop could not start its bundled runtime. Try NearDrop.cmd for more details. Windows 10/11 x64 is required.",L"NearDrop",MB_OK|MB_ICONERROR);return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess,INFINITE);
    DWORD code=0;GetExitCodeProcess(process.hProcess,&code);CloseHandle(process.hProcess);
    if(code!=0 && code!=0xC000013A){MessageBoxW(NULL,L"NearDrop stopped with an error. It may already be running. Close any existing NearDrop window, then try again. Use NearDrop.cmd to see detailed startup messages.",L"NearDrop",MB_OK|MB_ICONINFORMATION);}
    return (int)code;
}

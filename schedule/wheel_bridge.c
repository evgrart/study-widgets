/* Mouse movement never crosses into Python or waits for the Tk UI thread. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <stdint.h>

#define TARGETS 16
#define QUEUE_SIZE 256
typedef struct { HWND panel; int token,head,count; int deltas[QUEUE_SIZE]; } Target;
static Target targets[TARGETS];
static CRITICAL_SECTION lock;
static HINSTANCE module;
static HANDLE thread,ready;
static DWORD thread_id;
static HHOOK hook;
static int serial;

static LRESULT CALLBACK mouse_proc(int code,WPARAM message,LPARAM data) {
    if(code>=0 && message==WM_MOUSEWHEEL) {
        const MSLLHOOKSTRUCT *info=(const MSLLHOOKSTRUCT*)data;
        HWND hit=WindowFromPoint(info->pt);
        DWORD pid=0;
        GetWindowThreadProcessId(hit,&pid);
        if(pid==GetCurrentProcessId()) {
            EnterCriticalSection(&lock);
            for(int i=0;i<TARGETS;i++) {
                Target *t=&targets[i]; RECT r;
                if(!t->token || !IsWindowVisible(t->panel) ||
                   !GetWindowRect(t->panel,&r) || !PtInRect(&r,info->pt) ||
                   GetAncestor(hit,GA_ROOT)!=GetAncestor(t->panel,GA_ROOT)) continue;
                int delta=(SHORT)HIWORD(info->mouseData);
                if(t->count<QUEUE_SIZE) {
                    t->deltas[(t->head+t->count)%QUEUE_SIZE]=delta;t->count++;
                } else t->deltas[(t->head+t->count-1)%QUEUE_SIZE]+=delta;
                LeaveCriticalSection(&lock);
                return 1;
            }
            LeaveCriticalSection(&lock);
        }
    }
    return CallNextHookEx(NULL,code,message,data);
}

static DWORD WINAPI worker(void *unused) {
    (void)unused;MSG msg;
    SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    PeekMessageW(&msg,NULL,0,0,PM_NOREMOVE);
    hook=SetWindowsHookExW(WH_MOUSE_LL,mouse_proc,module,0);
    SetEvent(ready);
    if(hook) {
        while(GetMessageW(&msg,NULL,0,0)>0) {TranslateMessage(&msg);DispatchMessageW(&msg);}
        UnhookWindowsHookEx(hook);hook=NULL;
    }
    return 0;
}

__declspec(dllexport) int WheelRegister(HWND panel) {
    int token=0;
    EnterCriticalSection(&lock);
    for(int i=0;i<TARGETS;i++) if(!targets[i].token) {
        Target *t=&targets[i];ZeroMemory(t,sizeof(*t));t->panel=panel;
        token=t->token=++serial;break;
    }
    if(token && !thread) {
        ready=CreateEventW(NULL,TRUE,FALSE,NULL);
        thread=CreateThread(NULL,0,worker,NULL,0,&thread_id);
        if(thread)WaitForSingleObject(ready,3000);
        CloseHandle(ready);ready=NULL;
    }
    if(!hook) {
        for(int i=0;i<TARGETS;i++) if(targets[i].token==token)targets[i].token=0;
        token=0;
    }
    LeaveCriticalSection(&lock);
    return token;
}

__declspec(dllexport) int WheelPoll(int token,int *delta) {
    int found=0;
    EnterCriticalSection(&lock);
    for(int i=0;i<TARGETS;i++) {
        Target *t=&targets[i];
        if(t->token==token && t->count) {
            *delta=t->deltas[t->head];t->head=(t->head+1)%QUEUE_SIZE;t->count--;found=1;break;
        }
    }
    LeaveCriticalSection(&lock);
    return found;
}

__declspec(dllexport) void WheelUnregister(int token) {
    HANDLE stopped=NULL;
    EnterCriticalSection(&lock);
    int active=0;
    for(int i=0;i<TARGETS;i++) {
        if(targets[i].token==token)ZeroMemory(&targets[i],sizeof(Target));
        if(targets[i].token)active++;
    }
    if(!active && thread) {
        PostThreadMessageW(thread_id,WM_QUIT,0,0);stopped=thread;
        thread=NULL;thread_id=0;
    }
    LeaveCriticalSection(&lock);
    if(stopped) {WaitForSingleObject(stopped,3000);CloseHandle(stopped);}
}

static LRESULT CALLBACK filtered_subclass(HWND h,UINT m,WPARAM p,LPARAM l,
                                         UINT_PTR id,DWORD_PTR callback) {
    if(m==WM_NCDESTROY || m==WM_MOUSEWHEEL || m==WM_GESTURE || m==WM_VSCROLL) {
        SUBCLASSPROC delegate=(SUBCLASSPROC)(uintptr_t)callback;
        if(delegate)return delegate(h,m,p,l,id,0);
    }
    return DefSubclassProc(h,m,p,l);
}

__declspec(dllexport) void *WheelSubclassProc(void) {return (void*)filtered_subclass;}
__declspec(dllexport) DWORD WheelThreadId(void) {return thread_id;}

BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved) {
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        module=instance;InitializeCriticalSection(&lock);DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}

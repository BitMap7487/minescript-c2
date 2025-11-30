import minescript
import threading
import importlib
import sys
import os

class JobManager:
    def __init__(self, script_dir, send_callback):
        self.script_dir = script_dir
        self.send_to_ui = send_callback
        self.active_jobs = {}
        
        # Debug: Show exactly where we are looking
        minescript.echo(f"📂 [JobMgr] Script folder: {self.script_dir}")
        
        if not os.path.exists(self.script_dir):
            minescript.echo(f"⚠️ [JobMgr] Folder not found. Creating: {self.script_dir}")
            os.makedirs(self.script_dir)

    def get_ui_config(self):
        script_buttons = []
        found_files = []
        
        if os.path.exists(self.script_dir):
            for filename in os.listdir(self.script_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    script_name = filename[:-3]
                    found_files.append(script_name)
                    script_buttons.append({
                        "label": f"▶ {script_name.capitalize()}", 
                        "type": "JOB", 
                        "payload": {"script": script_name, "action": "start"}, 
                        "style": "btn-success"
                    })
        
        if not found_files:
            minescript.echo(f"⚠️ [JobMgr] No .py scripts found in {self.script_dir}")
        else:
            minescript.echo(f"✅ [JobMgr] Found scripts: {found_files}")

        return [
            {
                "group": "📂 Scripts",
                "buttons": script_buttons
            },
            {
                "group": "🛑 Controls",
                "buttons": [
                    {"label": "🛑 STOP ALL", "type": "JOB", "payload": {"action": "stop_all"}, "style": "btn-warning"},
                    {"label": "♻️ RELOAD UI", "type": "CMD", "payload": "reload_ui", "style": ""}
                ]
            }
        ]

    def start_job(self, script_name):
        if script_name in self.active_jobs:
            self.send_to_ui("LOG_MSG", f"⚠️ {script_name} is already running.")
            return

        try:
            if self.script_dir not in sys.path:
                sys.path.append(os.path.abspath(self.script_dir))

            if script_name in sys.modules:
                module = importlib.reload(sys.modules[script_name])
            else:
                module = importlib.import_module(script_name)

            stop_event = threading.Event()
            t = threading.Thread(target=module.run, args=(stop_event,), daemon=True)
            t.start()

            self.active_jobs[script_name] = {"thread": t, "event": stop_event}
            self.send_to_ui("LOG_MSG", f"🚀 Started {script_name}")
            minescript.echo(f"Started {script_name}")

        except Exception as e:
            msg = f"❌ Error starting {script_name}: {e}"
            self.send_to_ui("LOG_MSG", msg)
            minescript.echo(msg)

    def stop_job(self, script_name):
        if script_name not in self.active_jobs: return

        job = self.active_jobs[script_name]
        job["event"].set()
        job["thread"].join(timeout=1.0)
        del self.active_jobs[script_name]
        
        self.send_to_ui("LOG_MSG", f"⏹️ Stopped {script_name}")

    def stop_all_jobs(self):
        for name in list(self.active_jobs.keys()):
            self.stop_job(name)

    def handle_task(self, task):
        t_type = task.get('type')
        payload = task.get('payload')

        if t_type == 'JOB':
            action = payload.get('action')
            if action == 'start': self.start_job(payload.get('script'))
            elif action == 'stop_all': self.stop_all_jobs()
        
        elif t_type == 'CMD':
            if payload == 'reload_ui':
                self.send_to_ui("UI_CONFIG", self.get_ui_config())
            elif payload == 'status':
                active = ", ".join(self.active_jobs.keys()) or "None"
                self.send_to_ui("LOG_MSG", f"Active Jobs: {active}")
                
        elif t_type == 'SAY':
            minescript.chat(str(payload))
            self.send_to_ui("CHAT_MSG", f"[Me] {payload}")

    #Exit entirely, including dashboard
        elif t_type == 'EXIT':
            self.stop_all_jobs()
            minescript.echo("Exiting Job Manager and Dashboard.")
            os._exit(0)
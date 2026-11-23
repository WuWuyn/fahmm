import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import psutil
import requests
from config.settings import ROOT, HOST, MODELS, DEFAULT_FORM
from core import llm
from core.pipeline import run_pipeline
from core.export import export_all, report_text

def ensure_server():
    try:
        requests.get(HOST + '/api/version',timeout=2).raise_for_status(); return
    except requests.RequestException:
        pass
    exe = Path(os.environ.get('LOCALAPPDATA','')) / 'Programs/Ollama/ollama.exe'
    if not exe.exists(): raise RuntimeError('Không tìm thấy Ollama. Hãy cài từ https://ollama.com/download/windows')
    env = os.environ.copy(); env.update({'OLLAMA_HOST':'127.0.0.1:11435','OLLAMA_MODELS':str(ROOT/'models'),'OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1'})
    (ROOT/'models').mkdir(exist_ok=True); (ROOT/'logs').mkdir(exist_ok=True)
    with open(ROOT/'logs'/'ollama-start.log','a',encoding='utf-8') as log:
        subprocess.Popen([str(exe),'serve'],env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(30):
        time.sleep(1)
        try: requests.get(HOST+'/api/version',timeout=1).raise_for_status(); return
        except requests.RequestException: pass
    raise RuntimeError('Không khởi động được Ollama tại cổng 11435; xem logs/ollama-start.log')

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('ReportAI Local Test'); self.geometry('1040x760'); self.minsize(800,600)
        self.configure(bg='#f2f5f5'); self.events=queue.Queue(); self.busy=False; self.cancel=threading.Event(); self.files=[]; self.result=None; self.bench=[]
        self.model=tk.StringVar(value=MODELS[0]); self.status=tk.StringVar(value='Đang kiểm tra Ollama…'); self.gpu=tk.BooleanVar(value=False)
        style=ttk.Style(self); style.theme_use('clam'); style.configure('TNotebook.Tab',padding=(18,10)); style.configure('TButton',padding=(10,6)); style.configure('Heading.TLabel',font=('Segoe UI',15,'bold')); style.configure('TLabel',font=('Segoe UI',10)); style.configure('Treeview',rowheight=27)
        header=ttk.Frame(self,padding=(20,12)); header.pack(fill='x'); ttk.Label(header,text='ReportAI Local Test',style='Heading.TLabel').pack(side='left'); ttk.Label(header,textvariable=self.status).pack(side='right')
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill='both',expand=True,padx=20,pady=(0,20))
        self.models_tab(); self.docs_tab(); self.results_tab(); self.bench_tab(); self.after(100,self.drain); self.task(self.connect)

    def models_tab(self):
        t=ttk.Frame(self.tabs,padding=18); self.tabs.add(t,text='Quản lý model')
        ttk.Label(t,text='Model trên máy',style='Heading.TLabel').pack(anchor='w'); ttk.Label(t,text='Kho riêng trên ổ D • Chọn một model cho mỗi lượt xử lý').pack(anchor='w',pady=(2,12))
        self.tree=ttk.Treeview(t,columns=('state',),show='tree headings',height=5); self.tree.heading('#0',text='Model'); self.tree.heading('state',text='Trạng thái'); self.tree.column('#0',width=560); self.tree.column('state',width=140); self.tree.pack(fill='x')
        for model in MODELS: self.tree.insert('', 'end', iid=model,text=model,values=('Đang kiểm tra',))
        buttons=ttk.Frame(t); buttons.pack(fill='x',pady=14)
        ttk.Button(buttons,text='Chọn model',command=self.choose_model).pack(side='left',padx=(0,8)); ttk.Button(buttons,text='Tải model đã chọn',command=self.pull).pack(side='left',padx=(0,8)); ttk.Button(buttons,text='Giải phóng model',command=lambda:self.task(self.unload_all)).pack(side='left',padx=(0,8)); ttk.Button(buttons,text='Làm mới',command=lambda:self.task(self.refresh)).pack(side='left')
        ttk.Checkbutton(t,text='Dùng GPU nếu tương thích (mặc định CPU)',variable=self.gpu).pack(anchor='w',pady=8)
        self.hardware=ttk.Label(t,text=''); self.hardware.pack(anchor='w',pady=8)
        ttk.Label(t,text='Chỉ quản lý các model trong dịch vụ riêng của ứng dụng.').pack(anchor='w')

    def docs_tab(self):
        t=ttk.Frame(self.tabs,padding=18); self.tabs.add(t,text='Xử lý tài liệu')
        ttk.Label(t,text='Tài liệu đầu vào',style='Heading.TLabel').pack(anchor='w')
        row=ttk.Frame(t); row.pack(fill='x',pady=8); ttk.Button(row,text='Thêm tài liệu',command=self.add_files).pack(side='left'); ttk.Button(row,text='Xóa danh sách',command=self.clear_files).pack(side='left',padx=8)
        self.files_label=ttk.Label(row,text='Chưa chọn tài liệu'); self.files_label.pack(side='left',padx=8)
        self.file_list=tk.Listbox(t,height=5,font=('Segoe UI',10)); self.file_list.pack(fill='x')
        row=ttk.Frame(t); row.pack(fill='x',pady=(12,4)); ttk.Label(row,text='Model:').pack(side='left'); ttk.Combobox(row,textvariable=self.model,values=MODELS,state='readonly',width=40).pack(side='left',padx=8)
        ttk.Label(t,text='Form mẫu có thể chỉnh sửa (được kèm trong báo cáo)').pack(anchor='w',pady=(8,4))
        self.form=tk.Text(t,height=7,wrap='word',font=('Segoe UI',10)); self.form.insert('1.0',DEFAULT_FORM); self.form.pack(fill='both',expand=True)
        row=ttk.Frame(t); row.pack(fill='x',pady=10); ttk.Button(row,text='Tải form TXT/Markdown',command=self.load_form).pack(side='left'); ttk.Button(row,text='Bắt đầu tổng hợp',command=self.start).pack(side='left',padx=8); ttk.Button(row,text='Hủy sau đoạn hiện tại',command=self.cancel.set).pack(side='left')
        self.progress=ttk.Progressbar(t,maximum=100); self.progress.pack(fill='x'); self.detail=ttk.Label(t,text='Sẵn sàng.'); self.detail.pack(anchor='w',pady=5)

    def results_tab(self):
        t=ttk.Frame(self.tabs,padding=18); self.tabs.add(t,text='Kết quả')
        row=ttk.Frame(t); row.pack(fill='x'); ttk.Label(row,text='Báo cáo và nguồn',style='Heading.TLabel').pack(side='left'); ttk.Button(row,text='Xuất Word, Markdown, JSON và Excel',command=self.export).pack(side='right')
        self.output=tk.Text(t,wrap='word',font=('Segoe UI',10)); scroll=ttk.Scrollbar(t,command=self.output.yview); self.output.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); self.output.pack(fill='both',expand=True,pady=12); self.output.insert('1.0','Kết quả và cảnh báo sẽ xuất hiện tại đây sau khi xử lý.')

    def bench_tab(self):
        t=ttk.Frame(self.tabs,padding=18); self.tabs.add(t,text='Benchmark')
        ttk.Label(t,text='So sánh ba model',style='Heading.TLabel').pack(anchor='w'); ttk.Label(t,text='Chạy tuần tự cùng danh sách tài liệu trong tab Xử lý tài liệu.').pack(anchor='w',pady=8)
        row=ttk.Frame(t); row.pack(fill='x',pady=8); ttk.Button(row,text='Chạy benchmark',command=self.start_bench).pack(side='left'); ttk.Button(row,text='Hủy sau đoạn hiện tại',command=self.cancel.set).pack(side='left',padx=8); ttk.Button(row,text='Xuất Excel',command=self.export_bench).pack(side='left')
        self.bench_tree=ttk.Treeview(t,columns=('time','speed','facts','status'),show='headings');
        for key,label,width in [('time','Giây',100),('speed','Token/giây',120),('facts','Dữ kiện có nguồn',130),('status','Model / trạng thái',480)]: self.bench_tree.heading(key,text=label); self.bench_tree.column(key,width=width)
        self.bench_tree.pack(fill='both',expand=True,pady=8)
        ttk.Label(t,text='JSON được kiểm tra theo schema. Chất lượng cần đối chiếu với đáp án chuẩn.').pack(anchor='w')

    def task(self, fn):
        if self.busy: messagebox.showinfo('Đang xử lý','Vui lòng đợi tác vụ hiện tại kết thúc.'); return
        self.busy=True
        def run():
            try: fn()
            except Exception as e: self.events.put(('error',str(e)))
            finally: self.events.put(('done',None))
        threading.Thread(target=run,daemon=True).start()
    def drain(self):
        try:
            while True:
                typ,val=self.events.get_nowait()
                if typ=='error': self.status.set('Có lỗi'); messagebox.showerror('Không thể xử lý',val)
                elif typ=='done': self.busy=False
                elif typ=='status': self.status.set(val)
                elif typ=='refresh':
                    for m in MODELS: self.tree.set(m,'state','Đã tải' if m.lower() in [v.lower() for v in val] else 'Chưa tải')
                    mem=psutil.virtual_memory(); self.hardware.config(text=f'RAM: {mem.total/1024**3:.1f} GB • còn trống {mem.available/1024**3:.1f} GB')
                elif typ=='progress': self.progress['value']=val[0]/max(val[1],1)*100; self.detail.config(text=val[2])
                elif typ=='result': self.result=val; self.output.delete('1.0','end'); self.output.insert('1.0',report_text(val,self.form.get('1.0','end'))); self.tabs.select(2); self.progress['value']=100
                elif typ=='bench': self.bench.append(val); self.bench_tree.insert('','end',values=(val['seconds'],val['tokens_per_second'],val['facts'],val['model']+' / '+val['status']))
        except queue.Empty: pass
        self.after(100,self.drain)
    def connect(self): ensure_server(); self.refresh()
    def refresh(self): self.events.put(('refresh',llm.tags())); self.events.put(('status','Ollama sẵn sàng • 127.0.0.1:11435'))
    def choose_model(self):
        selected=self.tree.selection()
        if selected: self.model.set(selected[0]); self.status.set('Đã chọn ' + selected[0])
    def pull(self):
        selected=self.tree.selection()
        if not selected: messagebox.showinfo('Chọn model','Chọn model trong danh sách.'); return
        model=selected[0]
        def work():
            self.events.put(('status','Đang tải '+model+'…'))
            with requests.post(HOST+'/api/pull',json={'model':model,'stream':True},stream=True,timeout=(10,600)) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        item=json.loads(line)
                        if 'error' in item: raise RuntimeError(item['error'])
            self.refresh()
        self.task(work)
    def unload_all(self):
        for m in llm.running(): llm.unload(m)
        self.events.put(('status','Đã giải phóng model của ứng dụng'))
    def add_files(self):
        for p in filedialog.askopenfilenames(filetypes=[('Tài liệu','*.pdf *.docx *.xlsx *.txt *.md'),('Tất cả','*.*')]):
            if p not in self.files: self.files.append(p); self.file_list.insert('end',p)
        self.files_label.config(text=f'{len(self.files)} tài liệu')
    def clear_files(self): self.files.clear(); self.file_list.delete(0,'end'); self.files_label.config(text='Chưa chọn tài liệu')
    def load_form(self):
        p=filedialog.askopenfilename(filetypes=[('Văn bản','*.txt *.md')])
        if p:
            try: self.form.delete('1.0','end'); self.form.insert('1.0',Path(p).read_text(encoding='utf-8-sig'))
            except Exception as e: messagebox.showerror('Lỗi đọc form',str(e))
    def start(self):
        if not self.files: messagebox.showinfo('Thiếu tài liệu','Hãy chọn ít nhất một tài liệu.'); return
        paths=list(self.files); model=self.model.get(); gpu=self.gpu.get(); self.cancel.clear()
        def work():
            self.events.put(('status','Đang xử lý tài liệu…'))
            result=run_pipeline(paths,model,lambda *a:self.events.put(('progress',a)),self.cancel,gpu)
            if not result['facts']: raise RuntimeError('Không có dữ kiện được xác thực. '+ '; '.join(x['reason'] for x in result['warnings'][:3]))
            self.events.put(('result',result)); self.events.put(('status','Hoàn tất • cần đối chiếu nguồn'))
        self.task(work)
    def export(self):
        if not self.result: messagebox.showinfo('Chưa có kết quả','Hãy xử lý tài liệu trước.'); return
        p=filedialog.askdirectory(initialdir=str(ROOT/'outputs'),title='Chọn thư mục xuất')
        if p:
            try: export_all(self.result,p,self.form.get('1.0','end')); messagebox.showinfo('Đã xuất',f'Đã xuất 4 tệp vào {p}')
            except Exception as e: messagebox.showerror('Lỗi xuất',str(e))
    def start_bench(self):
        if not self.files: messagebox.showinfo('Thiếu tài liệu','Chọn tài liệu trong tab Xử lý tài liệu.'); return
        paths=list(self.files); gpu=self.gpu.get(); self.cancel.clear(); self.bench=[]
        for item in self.bench_tree.get_children(): self.bench_tree.delete(item)
        def work():
            for model in MODELS:
                if self.cancel.is_set(): break
                self.events.put(('status','Benchmark '+model))
                try:
                    result=run_pipeline(paths,model,lambda *a:self.events.put(('progress',a)),self.cancel,gpu)
                    m=result['metrics']; row={'model':model,'seconds':m['seconds'],'tokens_per_second':m['tokens_per_second'],'facts':len(result['facts']),'status':'JSON hợp lệ' if result['facts'] else 'Không có dữ kiện hợp lệ'}
                except Exception as e: row={'model':model,'seconds':None,'tokens_per_second':None,'facts':0,'status':str(e)}
                self.events.put(('bench',row))
            self.events.put(('status','Benchmark đã kết thúc'))
        self.task(work)
    def export_bench(self):
        if not self.bench: messagebox.showinfo('Chưa có benchmark','Chạy benchmark trước.'); return
        p=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')])
        if p:
            from openpyxl import Workbook
            wb=Workbook(); ws=wb.active; ws.title='Benchmark'; ws.append(['Model','Giây','Token/giây','Dữ kiện có nguồn','Trạng thái'])
            for row in self.bench: ws.append([row[k] for k in ('model','seconds','tokens_per_second','facts','status')])
            ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions; wb.save(p)

def main():
    (ROOT/'outputs').mkdir(exist_ok=True); App().mainloop()

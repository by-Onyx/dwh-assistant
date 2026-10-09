"""General mode checks, actual outputs and tool traces; no claims of expert grading."""
import argparse,json,time,sys
from datetime import datetime
from pathlib import Path
from assistant import Agent,Client,EventLog,ROOT
sys.stdout.reconfigure(encoding="utf-8")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--backend",choices=["local-4b","local-3b","local-1.5b","openrouter"],default="local-4b")
    args=p.parse_args()
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    log=EventLog(ROOT/"logs"/f"general_{args.backend}_{stamp}.log")
    agent=Agent(Client(args.backend,max_tokens=2200),"general",log)
    cases=[
        ("pharmacy_questions",(ROOT/"examples/pharmacy.txt").read_text(encoding="utf-8"),"requirements",False),
        ("pharmacy_design",(ROOT/"examples/pharmacy_followup.txt").read_text(encoding="utf-8"),"modeling",False),
        ("logistics","Предложи предварительный DWH для логистики. Допущения: есть заявки на перевозку, рейсы, события погрузки/доставки с временем, справочники машин, водителей и маршрутов; ежедневные снимки доступности машин. Нужны своевременность доставки, длительность рейсов и загрузка автопарка. Укажи отдельные факты и grain, измерения и формулы. Не используй учебные таблицы продаж.", "modeling",True),
        ("education","Предложи предварительный DWH для университета. Есть студенты, курсы, регистрации студентов на курсы, занятия, посещаемость и попытки сдачи экзаменов. Нужны посещаемость и успеваемость. Не все студенты сдавали экзамен; допускаются повторные попытки. Укажи факты с точным grain, общие измерения и корректные знаменатели метрик. Допущения отметь. Не используй учебный каталог продаж.","modeling",True),
    ]
    rows=[]
    for case,q,topic,reset in cases:
        if reset: agent.reset()
        log.write("case_start",case=case)
        began=time.monotonic()
        row={"case":case,"backend":args.backend}
        try:
            result=agent.ask(q)
            calls=result["calls"]
            row.update(completed=True,tool_ok=any(c["name"]=="rules" and c["arguments"]=={"topic":topic} for c in calls),no_demo_catalog=all(c["name"]!="catalog" for c in calls),answer=result["answer"],repairs=result["repairs"])
        except Exception as exc:
            row.update(completed=False,tool_ok=False,no_demo_catalog=False,error=str(exc))
        row["seconds"]=round(time.monotonic()-began,2)
        rows.append(row)
        log.write("case_result",**row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    path=ROOT/"logs"/f"general_summary_{args.backend}_{stamp}.json"
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Summary:",path)
    return 0 if all(x["completed"] and x["tool_ok"] and x["no_demo_catalog"] for x in rows) else 1
if __name__=="__main__":
    raise SystemExit(main())

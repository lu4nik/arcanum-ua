#!/usr/bin/env python3
"""Ловить гендеровану граматику в репліках ГРАВЦЯ зі спільним (порожнім) полем 2.
Такі репліки бачать обидві статі, тож мають бути нейтральними.
Використання: python3 tools/genderlint.py [uk/dlg/файл ...]  (без арг. — всі)
Хибні спрацювання можливі (родові відмінки) — список для ОЧЕЙ, не для автозаміни."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arcfmt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
masc = re.compile(r'\b(я|Я)\b[^.!?]*?\b\w{2,}(ів|ав|ив|ув|юв|ов|івся|авсь|ався|ився|увався)\b')
fem  = re.compile(r'\b(я|Я)\b[^.!?]*?\b\w{2,}(ла|лась|лася)\b')
adj  = re.compile(r'\bя\b[^.!?]{0,30}\b(радий|готовий|певний|впевнений|згоден|винен|рада|готова|певна|згодна|винна)\b', re.I)
masc_pc = re.compile(r'\b(Живий|Живого|Живому|Живим|пане|добродію|сер|герой|героя|герою|Обранець|Обранця|Обранцю)\b')
fem_pc  = re.compile(r'\b(Жива|Живої|Живій|Живу|пані|панянко|героїня|героїні|героїню|Обраниця|Обраниці|Обраницю)\b')


def main():
    targets = sys.argv[1:] or [os.path.join(r, f) for r, _, fs in os.walk(os.path.join(ROOT, 'uk', 'dlg')) for f in sorted(fs)]
    n = 0
    for p in targets:
        if not p.endswith('.dlg'): continue
        for l in arcfmt.parse_dlg(open(p, 'rb').read()):
            if l['intelligence'].strip():
                if not l['female'].strip():
                    t = l['text'].decode('utf-8', 'replace')
                    hits = [k for k, rx in (('masc', masc), ('fem', fem), ('adj', adj)) if rx.search(t)]
                    if hits:
                        n += 1
                        print(f'{os.path.basename(p)} #{l["num"].decode()} [{",".join(hits)}]: {t[:90]}')
            else:
                # NPC: чоловічі маркери ГГ у жіночому полі і навпаки
                # (пророцтва/концепт «Живий» — легітимні: дивитись очима!)
                t_f = l['female'].decode('utf-8', 'replace')
                t_m = l['text'].decode('utf-8', 'replace')
                for label, rx, t in (('masc-у-жіночому', masc_pc, t_f), ('fem-у-чоловічому', fem_pc, t_m)):
                    m = rx.search(t)
                    if m:
                        n += 1
                        print(f'{os.path.basename(p)} #{l["num"].decode()} [{label} «{m.group(0)}»]: ...{t[max(0,m.start()-30):m.end()+20]}...')
    print(f'{n} підозрілих реплік')


if __name__ == '__main__':
    main()

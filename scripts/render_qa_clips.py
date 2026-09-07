#!/usr/bin/env python3
"""Renders a real ~3-minute-per-language clip for the [M6-2] listening QA pass (KANBAN
G5 gate). An actual human has to listen to these — nothing automated can substitute
for that, per M6-2's own acceptance criteria; this script only prepares the audio.

Each clip is a short, original 3-chapter story (not excerpted from any real book)
deliberately loaded with the kind of content the normalizers handle: cardinal/ordinal/
decimal numbers, percentages, currency, years, dates, negative temperatures,
abbreviations, an ALL-CAPS word, and a roman-numeral chapter heading — plus enough
paragraph/chapter breaks to exercise pause pacing (0.6s paragraph / 1.2s chapter) and
enough sentence variety to expose chunk-join artifacts (clicks/pops at chunk
boundaries).

Usage:
    python scripts/render_qa_clips.py
    python scripts/render_qa_clips.py --languages en,zh

Uses the real app data dir (so a re-run after fixing a normalizer bug reuses whatever
chunks didn't change, same as any other render) — run `python scripts/fetch_models.py`
first if models/ is empty.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.db import get_session, init_db  # noqa: E402
from app.ingest.document import DocBlock, DocChapter, Document  # noqa: E402
from app.ingest.persist import persist_document  # noqa: E402
from app.models import BlockKind  # noqa: E402
from app.pipeline.runner import PipelineError, create_job, run_job  # noqa: E402
from app.tts.pool import DEFAULT_WORKERS  # noqa: E402
from app.tts.registry import engine_for_language  # noqa: E402

# language -> (voice id, [(chapter title, [paragraph, ...]), ...])
_CLIPS: dict[str, tuple[str, list[tuple[str, list[str]]]]] = {
    "en": (
        "af_heart",
        [
            (
                "Chapter IV: The Ledger",
                [
                    "Mr. Whitfield opened the ledger to page 47 and ran his finger down the "
                    "column of figures. The harbor had handled 1,842 crates last month, an "
                    "increase of 12.5% over the same period in 1998. He noted that Dr. "
                    "Alvarez's shipment, worth $3,450.75, was due to arrive by 15 March at the "
                    "latest.",
                    "“It's remarkable,” he said, “that we've grown so much since "
                    "the ORIGINAL survey.” The word ORIGINAL, printed in bold capitals "
                    "across the old cover, still made him smile.",
                    "Outside, the temperature had dropped to -4 degrees, and the wind carried "
                    "the smell of salt and diesel across the dock.",
                    "By comparison, the neighboring port of St. Ives had logged only 1,203 "
                    "crates that same month, a shortfall of nearly 35%. Whitfield made a note "
                    "to mention this at the 22nd meeting of the harbor board, scheduled for "
                    "9 a.m. sharp.",
                    "A month earlier, on the 12th of February, a Prof. Ito had visited to "
                    "inspect the crane machinery, declaring it “sound, if a little rusty, for "
                    "a structure built circa 1975.” His report ran to some 18 pages, most of "
                    "them numbers Whitfield never quite understood.",
                ],
            ),
            (
                "Chapter V: The Storm",
                [
                    "By half past nine, the barometer read 987 millibars, and the radio "
                    "operator, no stranger to bad weather, counted down the minutes until "
                    "midnight. The captain, a veteran of some 30 years at sea, ordered the "
                    "crew to secure everything above deck.",
                    "Waves reaching nearly 6.5 meters battered the hull, and for the 3rd time "
                    "that week, the ship's log recorded a delay. Still, by 6 a.m. the storm had "
                    "passed, leaving behind a bill of roughly £2,100 in repairs.",
                    "The insurance adjuster, a Mrs. Patel from the regional office, later "
                    "estimated total damages at 1/3 of the original quote — roughly $700 once "
                    "the smaller repairs were tallied. “Could've been worse,” she remarked "
                    "dryly, filing the report under case No. 4471.",
                ],
            ),
            (
                "Chapter VI: Departure",
                [
                    "On the 1st of April, the ship finally left port, its cargo hold at 92% "
                    "capacity. Passengers numbering 214 in total lined the rails as the horn "
                    "sounded three times.",
                    "Etc., etc., thought Whitfield, watching the coastline shrink to a thin "
                    "grey line. He'd seen departures like this a hundred times, and yet each "
                    "one felt, somehow, like the first.",
                    "As the 4:15 tide carried them past the breakwater, someone in the crowd "
                    "shouted that the crossing would take “no more than 18 hours, give or "
                    "take.” Whitfield doubted it — closer to 22, by his own reckoning — but he "
                    "kept that to himself.",
                ],
            ),
        ],
    ),
    "pl": (
        "pl_PL-gosia-medium",
        [
            (
                "Rozdział IV: Księga rachunkowa",
                [
                    "Pan Kowalski otworzył księgę na stronie 47 i przesunął "
                    "palcem po kolumnie liczb. Port obsłużył w zeszłym "
                    "miesiącu 1842 skrzynie, co oznaczało wzrost o 12,5% względem "
                    "tego samego okresu w 1998 roku. Zauważył, że przesyłka "
                    "dr Nowak, warta 3450,75 złotych, miała dotrzeć najpóźniej "
                    "15 marca.",
                    "– To niesamowite – powiedział – jak bardzo "
                    "urośliśmy od PIERWOTNEGO badania. Słowo PIERWOTNE, "
                    "wydrukowane wielkimi literami na starej okładce, wciąż "
                    "wywoływało u niego uśmiech.",
                    "Na zewnątrz temperatura spadła do -4 stopni, a wiatr niósł "
                    "zapach soli i oleju napędowego znad nabrzeża.",
                    "Dla porównania, sąsiedni port w Ustce odnotował w tym samym "
                    "miesiącu jedynie 1203 skrzynie, co oznaczało spadek o prawie 35%. "
                    "Kowalski zanotował, by wspomnieć o tym na 22. posiedzeniu rady "
                    "portu, zaplanowanym na godzinę 9 rano.",
                    "Miesiąc wcześniej, 12 lutego, przyjechał prof. Kowal, aby "
                    "sprawdzić dźwigi portowe, uznając je za „sprawne, choć nieco "
                    "zardzewiałe, jak na konstrukcję z około 1975 roku”. Jego raport "
                    "liczył aż 18 stron, z których większość stanowiły liczby, "
                    "których Kowalski nigdy do końca nie rozumiał.",
                ],
            ),
            (
                "Rozdział V: Sztorm",
                [
                    "O wpół do dziesiątej barometr wskazywał 987 "
                    "hektopaskali, a radiotelegrafista, przyzwyczajony do złej pogody, "
                    "odliczał minuty do północy. Kapitan, weteran około 30 "
                    "lat pracy na morzu, kazał załodze zabezpieczyć wszystko na "
                    "pokładzie.",
                    "Fale sięgające niemal 6,5 metra uderzały w kadłub, a po "
                    "raz 3. w tym tygodniu dziennik pokładowy odnotował "
                    "opóźnienie. Mimo to, do godziny 6 rano sztorm ustał, "
                    "pozostawiając rachunek za naprawy na około 2100 złotych.",
                    "Rzeczoznawca ubezpieczeniowy, pani Zielińska z biura "
                    "regionalnego, oszacowała później szkody na 1/3 pierwotnej "
                    "wyceny — około 700 złotych po zsumowaniu mniejszych napraw. "
                    "– Mogło być gorzej – zauważyła sucho, archiwizując sprawę "
                    "pod nr 4471.",
                ],
            ),
            (
                "Rozdział VI: Odpłynięcie",
                [
                    "1 kwietnia statek w końcu opuścił port, z ładownią "
                    "wypełnioną w 92%. Łącznie 214 pasażerów "
                    "stało przy relingach, gdy syrena zabrzmiała trzykrotnie.",
                    "I tak dalej, i tak dalej, pomyślał Kowalski, patrząc, jak "
                    "linia brzegu kurczy się do cienkiej, szarej kreski. Widział "
                    "już setki takich odpłynięć, a mimo to każde z "
                    "nich wydawało się, jakoś, pierwsze.",
                    "Gdy przypływ o 4:15 poniósł ich za falochron, ktoś w tłumie "
                    "krzyknął, że przeprawa zajmie „nie więcej niż 18 godzin, plus "
                    "minus”. Kowalski w to wątpił — jego zdaniem bliżej było do 22 — "
                    "ale zachował to dla siebie.",
                ],
            ),
        ],
    ),
    "de": (
        "de_DE-thorsten-high",
        [
            (
                "Kapitel IV: Das Kontobuch",
                [
                    "Herr Weber schlug das Kontobuch auf Seite 47 auf und fuhr mit dem Finger "
                    "die Zahlenreihe entlang. Der Hafen hatte im letzten Monat 1.842 Kisten "
                    "abgefertigt, ein Anstieg von 12,5% gegenüber demselben Zeitraum im "
                    "Jahr 1998. Er bemerkte, dass die Sendung von Dr. Alvarez im Wert von "
                    "3.450,75 Euro spätestens am 15. März eintreffen sollte.",
                    "„Es ist erstaunlich“, sagte er, „wie sehr wir seit der "
                    "URSPRÜNGLICHEN Untersuchung gewachsen sind.“ Das Wort "
                    "URSPRÜNGLICHE, in fetten Großbuchstaben auf dem alten Einband "
                    "gedruckt, brachte ihn immer noch zum Lächeln.",
                    "Draußen war die Temperatur auf -4 Grad gefallen, und der Wind trug "
                    "den Geruch von Salz und Diesel über den Kai.",
                    "Zum Vergleich hatte der benachbarte Hafen von Sankt Peter im selben "
                    "Monat nur 1.203 Kisten verzeichnet, ein Rückgang von fast 35%. Weber "
                    "notierte sich, dies bei der 22. Sitzung des Hafenrats zu erwähnen, die "
                    "für 9 Uhr morgens angesetzt war.",
                    "Einen Monat zuvor, am 12. Februar, hatte Prof. Ito die Kranmaschinen "
                    "inspiziert und sie für „intakt, wenn auch etwas rostig, für eine "
                    "Anlage aus dem Jahr 1975“ erklärt. Sein Bericht umfasste rund "
                    "18 Seiten, die meisten davon Zahlen, die Weber nie ganz verstand.",
                ],
            ),
            (
                "Kapitel V: Der Sturm",
                [
                    "Um halb zehn zeigte das Barometer 987 Hektopascal, und der Funker, kein "
                    "Neuling bei schlechtem Wetter, zählte die Minuten bis Mitternacht "
                    "herunter. Der Kapitän, ein Veteran von etwa 30 Jahren auf See, befahl "
                    "der Mannschaft, alles an Deck zu sichern.",
                    "Wellen von fast 6,5 Metern schlugen gegen den Rumpf, und zum 3. Mal in "
                    "dieser Woche verzeichnete das Logbuch eine Verzögerung. Dennoch hatte "
                    "der Sturm bis 6 Uhr morgens nachgelassen und eine Reparaturrechnung von "
                    "etwa 2.100 Euro hinterlassen.",
                    "Die Versicherungsgutachterin, eine Frau Schmidt aus der Regionalstelle, "
                    "schätzte den Gesamtschaden später auf 1/3 des ursprünglichen Angebots — "
                    "etwa 700 Euro, nachdem die kleineren Reparaturen zusammengerechnet "
                    "waren. „Hätte schlimmer kommen können“, bemerkte sie trocken und "
                    "archivierte den Fall unter Nr. 4471. Es war bereits die 7. Verzögerung "
                    "in diesem Quartal, wie der Hafenmeister trocken anmerkte.",
                ],
            ),
            (
                "Kapitel VI: Die Abfahrt",
                [
                    "Am 1. April verließ das Schiff endlich den Hafen, sein Laderaum zu "
                    "92% gefüllt. Insgesamt 214 Passagiere standen an der Reling, als das "
                    "Horn dreimal ertönte.",
                    "Und so weiter, und so weiter, dachte Weber und sah zu, wie die Küste "
                    "zu einer dünnen grauen Linie zusammenschrumpfte. Er hatte solche "
                    "Abfahrten schon hundertmal erlebt, und doch fühlte sich jede einzelne "
                    "irgendwie wie die erste an.",
                    "Als die Flut um 4:15 Uhr sie an der Mole vorbeitrug, rief jemand in der "
                    "Menge, die Überfahrt werde „nicht mehr als 18 Stunden, mehr oder "
                    "weniger“ dauern. Weber bezweifelte das — seiner Einschätzung nach eher "
                    "22 —, behielt es aber für sich.",
                ],
            ),
        ],
    ),
    "zh": (
        "zf_xiaobei",
        [
            (
                "第四章:账本",
                [
                    "王先生翻开账本的第47页,手指沿着数字栏划过。上个月港口处理了1842箱货物,"
                    "比1998年同期增长了12.5%。他注意到,李博士的货物价值3450.75元,"
                    "最迟应在3月15日之前到达。",
                    "「真了不起,」他说,「自从最初的调查以来,我们发展得这么快。」"
                    "封面上用大写字母印着的「最初」这个词,依然让他会心一笑。",
                    "外面气温降到了零下4度,海风夹杂着盐味和柴油味,弥漫在码头上。",
                    "相比之下,邻近的圣彼得港同月只处理了1203箱货物,下降了将近35%。"
                    "王先生记下要在上午9点召开的第22次港务局会议上提起此事。",
                    "一个月前,也就是2月12日,伊藤教授曾来检查港口的起重机械,"
                    "称其「基本完好,只是有点生锈,毕竟是1975年左右建造的」。"
                    "他的报告长达18页,其中大部分是王先生始终没能完全看懂的数字。",
                ],
            ),
            (
                "第五章:风暴",
                [
                    "九点半,气压计显示987百帕,无线电员对恶劣天气早已习以为常,"
                    "默默倒数着到午夜的分钟。船长,一位有着约30年航海经验的老水手,"
                    "下令全体船员把甲板上的一切都固定好。",
                    "将近6.5米高的巨浪拍打着船体,这是本周第3次在航海日志中记录延误。"
                    "尽管如此,到清晨6点,风暴终于平息,留下了大约2100元的维修账单。",
                    "保险理赔员史女士后来估计,总损失约为原报价的三分之一——"
                    "把较小的维修费用加总后大约是700元。「没那么糟糕了,」"
                    "她冷冷地说道,把这起案件归档为第4471号。"
                    "港务长冷冷地补充道,这已经是本季度第7次延误了。",
                ],
            ),
            (
                "第六章:启航",
                [
                    "4月1日,船终于驶离港口,货舱装载率达到92%。"
                    "共有214名乘客站在船舷边,汽笛响了三声。",
                    "「等等等等,」王先生望着海岸线渐渐缩成一条细细的灰线,心里想道。"
                    "他见过上百次这样的启航,可每一次,却仍然觉得,仿佛是第一次。",
                    "当凌晨4点15分的潮水将船带过防波堤时,人群中有人喊道,这次航行"
                    "「最多18个小时,上下浮动」。王先生对此表示怀疑——"
                    "依他估计更接近22个小时——但他没有说出口。",
                ],
            ),
        ],
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--languages", default="en,pl,de,zh", help="comma-separated language codes")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"pool size (default: {DEFAULT_WORKERS})")
    args = parser.parse_args()

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    unknown = sorted(set(languages) - set(_CLIPS))
    if unknown:
        print(f"error: unknown language(s) {unknown}; supported: {sorted(_CLIPS)}", file=sys.stderr)
        return 1

    init_db()
    session_gen = get_session()
    session = next(session_gen)
    try:
        for language in languages:
            voice, chapters = _CLIPS[language]
            document = Document(
                title=f"QA Clip ({language})",
                language=language,
                chapters=[
                    DocChapter(
                        index=i, title=title,
                        blocks=[DocBlock(kind=BlockKind.para, text=p) for p in paragraphs],
                    )
                    for i, (title, paragraphs) in enumerate(chapters)
                ],
            )
            book = persist_document(session, document, Path(f"qa_clip_{language}.txt"), "txt")
            job = create_job(
                session, book, voice=voice, speed=1.0,
                engine_id=engine_for_language(language).id, formats=["mp3"],
            )
            print(f"Rendering {language} ({voice})...")
            try:
                output_path = run_job(session, job, workers=args.workers)
            except PipelineError as exc:
                print(f"  error: {exc}", file=sys.stderr)
                return 1
            print(f"  -> {output_path}")
    finally:
        session_gen.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

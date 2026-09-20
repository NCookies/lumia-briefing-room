"""지역명 판독 정확도를 전체 헤더 crop 에서 잰다. (plan-pvp 3단계)

정답은 군집 라벨(label_regions.py). 템플릿을 만든 샘플(이름당 최대 10장)은 전체의 일부라
나머지가 학습에 안 쓴 데이터다.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from label_regions import by_name, crop_text  # noqa: E402
from lumia_briefing_room.detect.region import load_region_templates, read_region, region_score  # noqa: E402


def main(hdr_dir, templates_path):
    templates = load_region_templates(Path(templates_path))
    ok = wrong = none = 0
    confusion = Counter()
    per = defaultdict(lambda: [0, 0, 0])
    for truth, members in by_name(hdr_dir).items():
        for f in members:
            got = read_region(region_score(crop_text(f)), templates).name
            if got is None:
                none += 1; per[truth][2] += 1
            elif got == truth:
                ok += 1; per[truth][0] += 1
            else:
                wrong += 1; per[truth][1] += 1; confusion[(truth, got)] += 1
    total = ok + wrong + none
    print(f"전체 {total}: 정답 {ok} ({ok/total:.1%}) / 오답 {wrong} ({wrong/total:.1%}) / 모름 {none} ({none/total:.1%})")
    for name, (a, b, c_) in sorted(per.items()):
        print(f"  {name:8} 정답 {a:3d} 오답 {b:2d} 모름 {c_:2d}")
    for (t, g), n in confusion.most_common(8):
        print("혼동:", t, "->", g, n)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

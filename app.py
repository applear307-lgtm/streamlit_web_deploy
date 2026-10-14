import json
import os
import random
import re
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="공중 보건 인식 설문", page_icon="🩺")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────────────────────
# 설정 (여기만 바꿔도 내용이 바뀌어요)
# ──────────────────────────────────────────────
# 당첨 확률(%) - 화면에는 공개하지 않아요. 합계 100
PRIZES = [
    ("초코에몽 250ml", 10.0),
    ("다이소 5,000원권", 5.0),
    ("박카스 F", 13.0),
    ("스타벅스 1만원권", 3.0),
    ("꽝", 69.0),
]

# 당첨 화면에 보여줄 이미지 (app.py 기준 상대 경로)
PRIZE_IMAGES = {
    "초코에몽": "images/prize_choco.png",
    "다이소 5,000원권": "images/prize_daiso.png",
    "박카스 F": "images/prize_bacchus.png",
    "스타벅스 1만원권": "images/prize_starbucks.png",
}

# 룰렛 화면 구성 (경품과 꽝은 각각 한 칸씩 표시)
# 실제 당첨 확률은 PRIZES의 가중치로 결정돼요.
WHEEL = [
    {"prize": "초코에몽", "label": "초코에몽", "color": "#8D5524", "text": "#FFFFFF"},
    {"prize": "다이소 5,000원권", "label": "다이소 5,000원", "color": "#E53935", "text": "#FFFFFF"},
    {"prize": "박카스 F", "label": "박카스 F", "color": "#1E4DB7", "text": "#FFFFFF"},
    {"prize": "스타벅스 1만원권", "label": "스타벅스 1만원", "color": "#00704A", "text": "#FFFFFF"},
    {"prize": "꽝", "label": "꽝", "color": "#ECEFF1", "text": "#546E7A"},
]
SPIN_SECONDS = 5.0  # 룰렛이 도는 시간(초)

Q1_OPTIONS = [
    "알고 있었다",
    "들어본 적은 있지만 정확한 뜻은 몰랐다",
    "처음 들어봤다",
]
Q2_OPTIONS = [
    "예방", "백신·예방접종", "감염병 관리", "위생·방역",
    "건강검진", "국가·정부의 역할", "금연·절주 캠페인", "잘 모르겠다",
]
Q3_OPTIONS = [
    "공중 보건이 더 우선시되어야 한다",
    "병원 치료가 더 우선시되어야 한다",
    "둘 다 똑같이 중요하다",
    "잘 모르겠다",
]
Q4_OPTIONS = [
    "감염병 확산 방지", "만성질환 예방", "의료비 절감",
    "건강 격차(불평등) 해소", "평균 수명 연장", "정신건강 증진",
    "응급·재난 대응", "잘 모르겠다", "딱히 효과가 없다고 생각한다"
]

# 구글 스프레드시트 탭 이름과 1행 제목 (시트와 똑같이 맞춰야 해요)
SHEET_RESPONSE = "응답_개편"
HEADER_RESPONSE = ["시각", "Q1 사전 인지", "Q2 공중 보건 연상", "Q3 우선순위", "Q3 이유", "Q4 효과", "Q4 기타"]
SHEET_WINNER = "당첨"
HEADER_WINNER = ["시각", "품목", "이메일"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SURVEY_URL = "https://public-health-survey.streamlit.app/"
SHARE_MESSAGE = (
    "🎁 공중 보건 인식 설문에 참여하고 룰렛도 돌려보세요! "
    "주변 친구들에게도 공유해 주세요 😊\n"
    f"{SURVEY_URL}"
)


def checkbox_multiselect(label: str, options: list, key_prefix: str) -> list:
    """접고 펼 수 있는 체크박스 목록에서 여러 항목을 선택해요."""
    selected = []
    with st.expander(label, expanded=False):
        st.caption("해당하는 항목을 모두 선택해 주세요.")
        for index, option in enumerate(options):
            if st.checkbox(option, key=f"{key_prefix}_{index}"):
                selected.append(option)
    return selected


# ──────────────────────────────────────────────
# 저장 (Google Sheets / secrets가 없으면 내 컴퓨터에 CSV로 저장)
# ──────────────────────────────────────────────
def sheets_enabled() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "sheet_id" in st.secrets
    except Exception:
        return False


@st.cache_resource
def get_spreadsheet():
    import gspread

    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return gc.open_by_key(st.secrets["sheet_id"])


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_row(sheet_name: str, header: list, row: list) -> bool:
    try:
        if sheets_enabled():
            import gspread

            book = get_spreadsheet()
            try:
                ws = book.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                ws = book.add_worksheet(title=sheet_name, rows=1000, cols=len(header))
                ws.append_row(header)
            ws.append_row(row, value_input_option="USER_ENTERED")
        else:
            path = f"{sheet_name}.csv"
            pd.DataFrame([row], columns=header).to_csv(
                path, mode="a", header=not os.path.exists(path),
                index=False, encoding="utf-8-sig",
            )
        return True
    except Exception as e:
        st.error(f"저장 중 오류가 발생했어요. 선생님께 알려주세요.\n\n{e}")
        return False


# ──────────────────────────────────────────────
# 룰렛
# ──────────────────────────────────────────────
def spin_prize() -> str:
    names = [p[0] for p in PRIZES]
    weights = [p[1] for p in PRIZES]
    return random.choices(names, weights=weights, k=1)[0]


WHEEL_HTML = """
<style>
  html, body { margin: 0; background: transparent;
    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; }
  .wrap { position: relative; width: 340px; height: 350px; margin: 0 auto; }
  .pointer { position: absolute; left: 50%; top: 2px; transform: translateX(-50%);
    width: 0; height: 0; z-index: 5;
    border-left: 15px solid transparent; border-right: 15px solid transparent;
    border-top: 30px solid #D32F2F;
    filter: drop-shadow(0 2px 2px rgba(0,0,0,.4)); }
  #wheel { position: absolute; left: 10px; top: 26px; width: 320px; height: 320px;
    border-radius: 50%; box-shadow: 0 4px 16px rgba(0,0,0,.35);
    transform: rotate(0deg); }
  #wheel svg { display: block; }
</style>
<div class="wrap">
  <div class="pointer"></div>
  <div id="wheel"><svg viewBox="0 0 320 320" width="320" height="320"></svg></div>
</div>
<script>
  const SEGS = __SEGS__;
  const TARGET = __TARGET__;      // -1 이면 돌지 않고 대기
  const DURATION = __DURATION__;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.querySelector("#wheel svg");
  const cx = 160, cy = 160, r = 156;
  const n = SEGS.length, a = 360 / n;

  function pt(deg, rad) {
    const t = deg * Math.PI / 180;
    return [cx + rad * Math.sin(t), cy - rad * Math.cos(t)];
  }

  SEGS.forEach(function (s, i) {
    const p1 = pt(i * a, r), p2 = pt((i + 1) * a, r);
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", "M" + cx + " " + cy + " L" + p1[0] + " " + p1[1] +
      " A" + r + " " + r + " 0 0 1 " + p2[0] + " " + p2[1] + " Z");
    path.setAttribute("fill", s.color);
    path.setAttribute("stroke", "#FFFFFF");
    path.setAttribute("stroke-width", "2");
    svg.appendChild(path);

    const g = document.createElementNS(NS, "g");
    g.setAttribute("transform", "rotate(" + ((i + 0.5) * a) + " " + cx + " " + cy + ")");
    const ty = cy - r * 0.58;
    const text = document.createElementNS(NS, "text");
    text.setAttribute("x", cx);
    text.setAttribute("y", ty);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dominant-baseline", "middle");
    text.setAttribute("transform", "rotate(-90 " + cx + " " + ty + ")");
    text.setAttribute("fill", s.text);
    text.setAttribute("font-size", s.label.length > 6 ? "13" : "16");
    text.setAttribute("font-weight", "700");
    text.textContent = s.label;
    g.appendChild(text);
    svg.appendChild(g);
  });

  // 가운데 원
  const hub = document.createElementNS(NS, "circle");
  hub.setAttribute("cx", cx); hub.setAttribute("cy", cy); hub.setAttribute("r", 20);
  hub.setAttribute("fill", "#FFFFFF"); hub.setAttribute("stroke", "#B0BEC5");
  hub.setAttribute("stroke-width", "3");
  svg.appendChild(hub);

  if (TARGET >= 0) {
    const wheel = document.getElementById("wheel");
    const center = (TARGET + 0.5) * a;
    const jitter = (Math.random() - 0.5) * a * 0.6;   // 칸 안에서 조금씩 다르게 멈추게
    const deg = 360 * 6 - center + jitter;            // 6바퀴 + 목표 칸이 위쪽 화살표 아래로
    setTimeout(function () {
      wheel.style.transition = "transform " + DURATION + "s cubic-bezier(0.15, 0.7, 0.1, 1)";
      wheel.style.transform = "rotate(" + deg + "deg)";
    }, 300);
  }
</script>
"""


def wheel_html(target_idx: int = -1) -> str:
    segs = [{"label": s["label"], "color": s["color"], "text": s["text"]} for s in WHEEL]
    return (
        WHEEL_HTML.replace("__SEGS__", json.dumps(segs, ensure_ascii=False))
        .replace("__TARGET__", str(target_idx))
        .replace("__DURATION__", str(SPIN_SECONDS))
    )


def show_prize_image(prize: str):
    rel = PRIZE_IMAGES.get(prize)
    if rel:
        path = os.path.join(BASE_DIR, rel)
        if os.path.exists(path):
            st.image(path, width=320, caption=prize)


def show_survey_share():
    st.markdown("### 📣 친구들에게도 설문을 공유해 주세요!")
    st.markdown(f"[설문 참여 링크 열기]({SURVEY_URL})")
    st.caption("아래 문구 오른쪽 위의 복사 아이콘을 누르면 문구와 링크가 함께 복사돼요.")
    st.code(SHARE_MESSAGE, language="text")


# ──────────────────────────────────────────────
# 세션 상태: survey → spin → result → done
# ──────────────────────────────────────────────
ss = st.session_state
ss.setdefault("stage", "survey")
ss.setdefault("prize", None)

st.title("🩺 공중 보건 인식 설문")

if not sheets_enabled():
    st.caption("⚠️ 테스트 모드: 구글 시트 연결 없이 이 컴퓨터에 CSV로 저장돼요.")

# ──────────────────────────────────────────────
# 1단계: 설문
# ──────────────────────────────────────────────
if ss.stage == "survey":
    st.caption("설문에 참여하면 룰렛을 돌릴 수 있어요! 🎁")

    with st.form("survey"):
        q1 = st.radio(
            "Q1. 이번 설문에 참여하기 전, '공중 보건'이라는 개념을 알고 있었나요? (필수)",
            Q1_OPTIONS,
            index=None,
        )

        st.info(
            "참고: WHO 헌장(1948) 전문은 건강을 단순히 질병이 없거나 허약하지 않은 상태만이 아니라, "
            "신체적·정신적·사회적으로 완전히 안녕한 상태로 설명합니다. 또한 전문은 사람들의 건강 증진을 위해 대중의 올바른 이해와 적극적 협력이 중요하고, 정부는 적절한 보건·사회적 조치를 통해 국민 건강을 책임져야 한다고 밝힙니다."
        )

        q2 = checkbox_multiselect(
            "Q2. '공중 보건'이라는 말을 들었을 때 떠오르는 것을 모두 골라주세요. (필수)",
            Q2_OPTIONS,
            "q2_option",
        )

        q3 = st.radio(
            "Q3. 공중 보건과 병원 치료 중 무엇이 더 우선시되어야 한다고 생각하나요? (필수)",
            Q3_OPTIONS,
            index=None,
        )
        q3_reason = st.text_area("그렇게 생각하는 이유 (선택)", height=80)

        q4 = checkbox_multiselect(
            "Q4. 공중 보건이 어디에 효과적이라고 생각하나요? (복수 선택) (필수)",
            Q4_OPTIONS,
            "q4_option",
        )
        q4_etc = st.text_input("Q4 기타 의견 (선택)")

        submitted = st.form_submit_button("제출하고 룰렛 돌리러 가기 🎰", type="primary")

    if submitted:
        if q1 is None or not q2 or q3 is None or not q4:
            st.warning("Q1, Q2, Q3, Q4 모두 답변해 주세요.")
        else:
            ok = save_row(
                SHEET_RESPONSE, HEADER_RESPONSE,
                [now_str(), q1, ", ".join(q2), q3, q3_reason, ", ".join(q4), q4_etc],
            )
            if ok:
                ss.stage = "spin"
                st.rerun()

# ──────────────────────────────────────────────
# 2단계: 룰렛
# ──────────────────────────────────────────────
elif ss.stage == "spin":
    st.success("설문에 참여해 주셔서 감사합니다! 🙌")
    st.subheader("🎰 룰렛을 돌려보세요")

    wheel_slot = st.empty()
    btn_slot = st.empty()

    with wheel_slot.container():
        components.html(wheel_html(-1), height=360)  # 대기 상태의 룰렛

    if btn_slot.button("룰렛 돌리기!", type="primary"):
        btn_slot.empty()

        # 결과는 클릭 시점에 서버에서 한 번만 결정 (새로고침해도 바뀌지 않아요)
        ss.prize = spin_prize()
        target = random.choice(
            [i for i, seg in enumerate(WHEEL) if seg["prize"] == ss.prize]
        )

        with wheel_slot.container():
            components.html(wheel_html(target), height=360)  # 돌아가는 룰렛

        time.sleep(SPIN_SECONDS + 2.2)  # 룰렛이 멈추고 잠깐 보여준 뒤 결과 화면으로
        ss.stage = "result"
        st.rerun()

# ──────────────────────────────────────────────
# 3단계: 결과 (당첨이면 이메일 입력)
# ──────────────────────────────────────────────
elif ss.stage == "result":
    prize = ss.prize

    if prize == "꽝":
        st.subheader("😢 아쉽게도 꽝이에요")
        st.write("다음 기회에 또 만나요. 설문에 참여해 주셔서 감사합니다!")
        ss.stage = "done"
    else:
        st.balloons()
        st.subheader(f"🎉 축하합니다! **{prize}** 당첨!")
        show_prize_image(prize)
        st.write("경품을 받을 이메일 주소를 입력해 주세요.")

        with st.form("winner"):
            email = st.text_input("이메일 주소", placeholder="example@email.com")
            agree = st.checkbox(
                "경품 전달 목적으로 이메일 주소를 수집·이용하는 데 동의합니다."
            )
            go = st.form_submit_button("제출", type="primary")

        if go:
            if not EMAIL_RE.match(email.strip()):
                st.warning("올바른 이메일 형식이 아니에요.")
            elif not agree:
                st.warning("개인정보 수집·이용에 동의해 주세요.")
            else:
                ok = save_row(
                    SHEET_WINNER, HEADER_WINNER,
                    [now_str(), prize, email.strip()],
                )
                if ok:
                    ss.stage = "done"
                    st.rerun()

        show_survey_share()

# ──────────────────────────────────────────────
# 4단계: 완료
# ──────────────────────────────────────────────
if ss.stage == "done":
    if ss.prize and ss.prize != "꽝":
        st.success(f"✅ {ss.prize} 당첨 정보가 접수되었어요!")
        show_prize_image(ss.prize)
        show_survey_share()
    st.info("참여해 주셔서 감사합니다. 창을 닫으셔도 좋아요.")

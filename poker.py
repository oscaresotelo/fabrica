import streamlit as st
import time
import json
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🃏 Poker Tournament Manager",
    page_icon="🃏",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=JetBrains+Mono:wght@400;700&display=swap');

:root {
    --green-felt:   #0d3320;
    --green-mid:    #1a5c38;
    --green-light:  #2d8653;
    --gold:         #c9a84c;
    --gold-light:   #e8c97a;
    --gold-dark:    #8b6914;
    --cream:        #f5edd6;
    --red-card:     #c0392b;
    --black-card:   #1a1a1a;
    --white:        #ffffff;
    --danger:       #e74c3c;
    --shadow:       0 8px 32px rgba(0,0,0,0.5);
}

html, body, [class*="css"] {
    font-family: 'Libre Baskerville', serif;
    background-color: var(--green-felt) !important;
    color: var(--cream) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a2818 0%, #0d3320 100%) !important;
    border-right: 2px solid var(--gold-dark);
}
[data-testid="stSidebar"] * { color: var(--cream) !important; }

/* Headers */
h1, h2, h3 { font-family: 'Playfair Display', serif !important; color: var(--gold) !important; }
h1 { font-size: 2.2rem !important; text-shadow: 0 2px 8px rgba(201,168,76,0.3); }

/* Metric cards */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1a4a2e 0%, #0d3320 100%);
    border: 1px solid var(--gold-dark);
    border-radius: 12px;
    padding: 1rem !important;
    box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"] { color: var(--gold-light) !important; font-size: 0.8rem !important; letter-spacing: 0.1em; text-transform: uppercase; }
[data-testid="stMetricValue"] { color: var(--cream) !important; font-family: 'JetBrains Mono', monospace !important; font-size: 1.8rem !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, var(--gold-dark), var(--gold)) !important;
    color: var(--black-card) !important;
    font-family: 'Playfair Display', serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.5rem !important;
    box-shadow: 0 4px 12px rgba(201,168,76,0.3) !important;
    transition: all 0.2s ease !important;
    letter-spacing: 0.05em;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 20px rgba(201,168,76,0.5) !important;
}

/* Danger button override via key class trick */
.danger-btn .stButton > button {
    background: linear-gradient(135deg, #8b0000, var(--danger)) !important;
    color: white !important;
}

/* Inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stTextArea textarea {
    background: #1a4a2e !important;
    color: var(--cream) !important;
    border: 1px solid var(--gold-dark) !important;
    border-radius: 8px !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #0a2818 !important;
    border-bottom: 2px solid var(--gold-dark) !important;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Playfair Display', serif !important;
    color: var(--gold-dark) !important;
    font-size: 1rem !important;
    padding: 0.8rem 1.5rem !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #1a4a2e, #0d3320) !important;
    color: var(--gold) !important;
    border-bottom: 3px solid var(--gold) !important;
}

/* Divider */
hr { border-color: var(--gold-dark) !important; opacity: 0.4; }

/* Timer display */
.timer-box {
    background: linear-gradient(135deg, #0a2818, #1a4a2e);
    border: 3px solid var(--gold);
    border-radius: 20px;
    padding: 2rem;
    text-align: center;
    box-shadow: 0 0 40px rgba(201,168,76,0.2), inset 0 0 60px rgba(0,0,0,0.3);
    margin-bottom: 1.5rem;
}
.timer-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 5rem;
    font-weight: 700;
    color: var(--gold-light);
    text-shadow: 0 0 20px rgba(201,168,76,0.5);
    letter-spacing: 0.1em;
    line-height: 1;
}
.timer-label {
    font-family: 'Playfair Display', serif;
    font-size: 1rem;
    color: var(--green-light);
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-top: 0.5rem;
}
.blind-display {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--cream);
    margin: 0.5rem 0;
}
.level-badge {
    display: inline-block;
    background: var(--gold);
    color: var(--black-card);
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 0.9rem;
    padding: 0.3rem 1.2rem;
    border-radius: 20px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}
.next-blind {
    font-family: 'Libre Baskerville', serif;
    font-size: 0.95rem;
    color: var(--gold-dark);
    margin-top: 0.5rem;
    font-style: italic;
}

/* Player cards */
.player-card {
    background: linear-gradient(135deg, #1a4a2e 0%, #0d3320 100%);
    border: 1px solid var(--gold-dark);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.player-name {
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--cream);
}
.player-chips {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1rem;
    color: var(--gold);
}
.player-out {
    opacity: 0.4;
    border-color: var(--red-card) !important;
    background: linear-gradient(135deg, #2a1a1a, #1a0a0a) !important;
}
.rank-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    background: var(--gold-dark);
    color: var(--cream);
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    margin-right: 0.5rem;
}

/* Prize table */
.prize-row {
    background: linear-gradient(90deg, #1a4a2e, #0d3320);
    border: 1px solid var(--gold-dark);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    margin-bottom: 0.3rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.prize-pos { font-family: 'Playfair Display', serif; color: var(--gold); font-weight: 700; }
.prize-amount { font-family: 'JetBrains Mono', monospace; color: var(--cream); font-size: 1.1rem; }

/* Alert / warning */
.stAlert { border-radius: 10px !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--green-felt); }
::-webkit-scrollbar-thumb { background: var(--gold-dark); border-radius: 3px; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid var(--gold-dark) !important; border-radius: 10px !important; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
def init_state():
    defaults = {
        # Tournament settings
        "tournament_name": "Torneo Póquer",
        "buyin_amount": 20,
        "buyin_chips": 10000,
        "rebuy_amount": 10,
        "rebuy_chips": 5000,
        "addon_amount": 15,
        "addon_chips": 8000,
        "addon_level_limit": 6,
        "rebuy_level_limit": 4,
        # Blind structure
        "blind_levels": [
            {"small": 25,   "big": 50,   "ante": 0,   "minutes": 20},
            {"small": 50,   "big": 100,  "ante": 10,  "minutes": 20},
            {"small": 75,   "big": 150,  "ante": 15,  "minutes": 20},
            {"small": 100,  "big": 200,  "ante": 25,  "minutes": 20},
            {"small": 150,  "big": 300,  "ante": 25,  "minutes": 20},
            {"small": 200,  "big": 400,  "ante": 50,  "minutes": 15},
            {"small": 300,  "big": 600,  "ante": 75,  "minutes": 15},
            {"small": 400,  "big": 800,  "ante": 100, "minutes": 15},
            {"small": 600,  "big": 1200, "ante": 150, "minutes": 12},
            {"small": 800,  "big": 1600, "ante": 200, "minutes": 12},
            {"small": 1000, "big": 2000, "ante": 300, "minutes": 10},
            {"small": 1500, "big": 3000, "ante": 500, "minutes": 10},
        ],
        # Timer
        "current_level": 0,
        "timer_running": False,
        "time_remaining": 0,
        "timer_start_wall": None,
        "timer_start_remaining": 0,
        # Players
        "players": [],
        "next_player_id": 1,
        # Tournament status
        "tournament_started": False,
        "tournament_finished": False,
        "total_pot": 0,
        # Payout structure (% of pot)
        "payout_structure": [
            {"place": 1, "pct": 50},
            {"place": 2, "pct": 30},
            {"place": 3, "pct": 20},
        ],
        # Log
        "event_log": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ── Helpers ───────────────────────────────────────────────────────────────────
def log_event(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.event_log.insert(0, f"[{ts}] {msg}")
    if len(st.session_state.event_log) > 100:
        st.session_state.event_log = st.session_state.event_log[:100]

def get_time_remaining():
    if not st.session_state.timer_running:
        return st.session_state.time_remaining
    elapsed = time.time() - st.session_state.timer_start_wall
    remaining = st.session_state.timer_start_remaining - elapsed
    return max(0, remaining)

def format_time(seconds):
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"

def active_players():
    return [p for p in st.session_state.players if p["active"]]

def eliminated_players():
    return [p for p in st.session_state.players if not p["active"]]

def total_chips_in_play():
    total = 0
    for p in st.session_state.players:
        total += p.get("chips", 0)
        total += p.get("rebuys", 0) * st.session_state.rebuy_chips
        total += p.get("addons", 0) * st.session_state.addon_chips
    # Better: use initial chips
    return st.session_state.total_pot / st.session_state.buyin_amount * st.session_state.buyin_chips if st.session_state.buyin_amount else 0

def avg_stack():
    ap = active_players()
    if not ap:
        return 0
    return st.session_state.total_chips_in_play / len(ap) if st.session_state.get("total_chips_in_play", 0) else 0

def calculate_prizes():
    prizes = []
    total = st.session_state.total_pot
    for row in st.session_state.payout_structure:
        prizes.append({
            "place": row["place"],
            "pct": row["pct"],
            "amount": round(total * row["pct"] / 100, 2)
        })
    return prizes

def start_level_timer(level_idx):
    mins = st.session_state.blind_levels[level_idx]["minutes"]
    st.session_state.time_remaining = mins * 60
    st.session_state.timer_start_remaining = mins * 60
    st.session_state.timer_start_wall = time.time()
    st.session_state.timer_running = True

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🃏 Poker Manager")
    st.markdown("---")

    # Quick stats
    ap = active_players()
    ep = eliminated_players()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Activos", len(ap))
    with col2:
        st.metric("Eliminados", len(ep))

    st.metric("Bote total", f"${st.session_state.total_pot:,.0f}")

    lvl = st.session_state.current_level
    if lvl < len(st.session_state.blind_levels):
        bl = st.session_state.blind_levels[lvl]
        st.metric("Nivel actual", f"Nivel {lvl + 1}")
        st.metric("Ciegas", f"{bl['small']:,} / {bl['big']:,}")
        if bl['ante']:
            st.metric("Ante", f"{bl['ante']:,}")

    st.markdown("---")

    if not st.session_state.tournament_started:
        if st.button("🚀 Iniciar Torneo", use_container_width=True):
            if len(st.session_state.players) < 2:
                st.error("Necesitas al menos 2 jugadores")
            else:
                st.session_state.tournament_started = True
                st.session_state.current_level = 0
                chips = st.session_state.buyin_chips
                for p in st.session_state.players:
                    p["chips"] = chips
                    p["active"] = True
                    p["rebuys"] = 0
                    p["addons"] = 0
                start_level_timer(0)
                log_event("🚀 Torneo iniciado")
                st.rerun()
    else:
        if not st.session_state.tournament_finished:
            st.markdown("**Control del torneo**")
            if st.session_state.timer_running:
                if st.button("⏸ Pausar", use_container_width=True):
                    st.session_state.time_remaining = get_time_remaining()
                    st.session_state.timer_running = False
                    log_event("⏸ Timer pausado")
            else:
                if st.button("▶ Reanudar", use_container_width=True):
                    st.session_state.timer_start_wall = time.time()
                    st.session_state.timer_start_remaining = st.session_state.time_remaining
                    st.session_state.timer_running = True
                    log_event("▶ Timer reanudado")

            if st.button("⏭ Siguiente nivel", use_container_width=True):
                lvl = st.session_state.current_level
                if lvl + 1 < len(st.session_state.blind_levels):
                    st.session_state.current_level = lvl + 1
                    start_level_timer(st.session_state.current_level)
                    log_event(f"⏭ Nivel {st.session_state.current_level + 1} iniciado")
                    st.rerun()

    st.markdown("---")
    if st.button("🔄 Reiniciar todo", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── MAIN TABS ─────────────────────────────────────────────────────────────────
tabs = st.tabs(["🎯 Torneo en vivo", "👥 Jugadores", "📊 Premios", "⚙️ Configuración", "📋 Registro"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: LIVE TOURNAMENT
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    if not st.session_state.tournament_started:
        st.markdown("## ♠ Bienvenido al Poker Tournament Manager")
        st.info("Configura el torneo en **⚙️ Configuración**, añade jugadores en **👥 Jugadores** y pulsa **🚀 Iniciar Torneo** en el panel lateral.")
    else:
        # Timer logic
        remaining = get_time_remaining()
        if remaining <= 0 and st.session_state.timer_running:
            st.session_state.timer_running = False
            st.session_state.time_remaining = 0
            st.warning("⏰ ¡Tiempo! El nivel ha terminado. Avanza al siguiente nivel.")

        lvl_idx = st.session_state.current_level
        bl = st.session_state.blind_levels[lvl_idx]

        # Refresh every second while running
        if st.session_state.timer_running:
            time.sleep(1)
            st.rerun()

        # ── Timer display ──
        next_lvl_text = ""
        if lvl_idx + 1 < len(st.session_state.blind_levels):
            nl = st.session_state.blind_levels[lvl_idx + 1]
            next_lvl_text = f"Siguiente: {nl['small']:,} / {nl['big']:,}" + (f" | Ante: {nl['ante']:,}" if nl['ante'] else "")

        ante_text = f" | Ante: {bl['ante']:,}" if bl["ante"] else ""

        st.markdown(f"""
        <div class="timer-box">
            <div class="level-badge">NIVEL {lvl_idx + 1}</div>
            <div class="blind-display">SB {bl['small']:,} &nbsp;/&nbsp; BB {bl['big']:,}{ante_text}</div>
            <div class="timer-time">{format_time(remaining)}</div>
            <div class="timer-label">{"▶ EN JUEGO" if st.session_state.timer_running else "⏸ PAUSADO"}</div>
            <div class="next-blind">{next_lvl_text}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Stats row ──
        ap = active_players()
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Jugadores activos", len(ap))
        with c2:
            st.metric("Bote total", f"${st.session_state.total_pot:,.0f}")
        with c3:
            total_chips = sum(p["chips"] for p in st.session_state.players if p["active"])
            avg = total_chips // len(ap) if ap else 0
            st.metric("Stack promedio", f"{avg:,}")
        with c4:
            biggest = max((p["chips"] for p in ap), default=0)
            st.metric("Stack mayor", f"{biggest:,}")

        st.markdown("---")

        # ── Active players quick view ──
        st.markdown("### ♦ Jugadores activos")
        if not ap:
            st.info("No hay jugadores activos.")
        else:
            # Sort by chips desc
            sorted_players = sorted(ap, key=lambda x: x["chips"], reverse=True)
            for i, p in enumerate(sorted_players):
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                rebuy_info = f" | Recompras: {p['rebuys']}" if p['rebuys'] else ""
                addon_info = f" | Add-ons: {p['addons']}" if p['addons'] else ""
                st.markdown(f"""
                <div class="player-card">
                    <div>
                        <span class="rank-badge">{rank_emoji}</span>
                        <span class="player-name">{p['name']}</span>
                        <span style="color: var(--gold-dark); font-size: 0.8rem;">{rebuy_info}{addon_info}</span>
                    </div>
                    <span class="player-chips">{p['chips']:,} fichas</span>
                </div>
                """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: PLAYERS
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("## 👥 Gestión de jugadores")

    # Add player
    with st.expander("➕ Añadir jugador", expanded=not st.session_state.tournament_started):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_name = st.text_input("Nombre del jugador", key="new_player_name", placeholder="Nombre...")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Añadir"):
                if new_name.strip():
                    pid = st.session_state.next_player_id
                    chips = st.session_state.buyin_chips if st.session_state.tournament_started else 0
                    st.session_state.players.append({
                        "id": pid,
                        "name": new_name.strip(),
                        "chips": chips,
                        "active": True,
                        "rebuys": 0,
                        "addons": 0,
                        "position": None,
                    })
                    st.session_state.next_player_id += 1
                    st.session_state.total_pot += st.session_state.buyin_amount
                    st.session_state.total_chips_in_play = st.session_state.total_chips_in_play + chips if "total_chips_in_play" in st.session_state else chips
                    log_event(f"➕ {new_name} se unió al torneo")
                    st.rerun()
                else:
                    st.error("Escribe un nombre válido")

    st.markdown("---")

    # Active players
    ap = active_players()
    ep = eliminated_players()

    if ap:
        st.markdown("### ✅ Jugadores activos")
        for p in sorted(ap, key=lambda x: x["chips"], reverse=True):
            with st.expander(f"**{p['name']}** — {p['chips']:,} fichas"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_chips = st.number_input(
                        "Fichas actuales",
                        min_value=0,
                        value=p["chips"],
                        step=100,
                        key=f"chips_{p['id']}"
                    )
                    if new_chips != p["chips"]:
                        p["chips"] = new_chips
                with col2:
                    st.markdown(f"**Recompras:** {p['rebuys']}")
                    lvl_idx = st.session_state.current_level
                    can_rebuy = lvl_idx < st.session_state.rebuy_level_limit
                    if st.session_state.tournament_started and can_rebuy:
                        if st.button(f"💰 Recompra (+{st.session_state.rebuy_chips:,})", key=f"rebuy_{p['id']}"):
                            p["rebuys"] += 1
                            p["chips"] += st.session_state.rebuy_chips
                            st.session_state.total_pot += st.session_state.rebuy_amount
                            log_event(f"💰 {p['name']} hizo recompra (#{p['rebuys']})")
                            st.rerun()
                    elif st.session_state.tournament_started:
                        st.caption("Recompras cerradas (nivel máximo)")
                with col3:
                    st.markdown(f"**Add-ons:** {p['addons']}")
                    can_addon = lvl_idx < st.session_state.addon_level_limit
                    if st.session_state.tournament_started and can_addon:
                        if st.button(f"⚡ Add-on (+{st.session_state.addon_chips:,})", key=f"addon_{p['id']}"):
                            p["addons"] += 1
                            p["chips"] += st.session_state.addon_chips
                            st.session_state.total_pot += st.session_state.addon_amount
                            log_event(f"⚡ {p['name']} hizo add-on (#{p['addons']})")
                            st.rerun()
                    elif st.session_state.tournament_started:
                        st.caption("Add-ons cerrados")

                st.markdown("---")
                if st.session_state.tournament_started:
                    if st.button(f"💀 Eliminar a {p['name']}", key=f"elim_{p['id']}"):
                        p["active"] = False
                        p["position"] = len(ep) + 1
                        remaining_active = [x for x in ap if x["active"] and x["id"] != p["id"]]
                        if len(remaining_active) == 1:
                            st.session_state.tournament_finished = True
                            winner = remaining_active[0]
                            log_event(f"🏆 ¡{winner['name']} gana el torneo!")
                        log_event(f"💀 {p['name']} eliminado en posición #{p['position']}")
                        st.rerun()
                else:
                    if st.button(f"🗑 Quitar a {p['name']}", key=f"remove_{p['id']}"):
                        st.session_state.players = [x for x in st.session_state.players if x["id"] != p["id"]]
                        st.session_state.total_pot = max(0, st.session_state.total_pot - st.session_state.buyin_amount)
                        log_event(f"🗑 {p['name']} retirado")
                        st.rerun()

    if ep:
        st.markdown("---")
        st.markdown("### 💀 Eliminados")
        for p in sorted(ep, key=lambda x: x.get("position", 99), reverse=True):
            pos = p.get("position", "?")
            st.markdown(f"""
            <div class="player-card player-out">
                <div>
                    <span class="rank-badge">#{pos}</span>
                    <span class="player-name">{p['name']}</span>
                </div>
                <span class="player-chips" style="color: var(--red-card)">ELIMINADO</span>
            </div>
            """, unsafe_allow_html=True)

    if st.session_state.tournament_finished:
        winners = [p for p in st.session_state.players if p["active"]]
        if winners:
            st.balloons()
            st.success(f"🏆 ¡{winners[0]['name']} gana el torneo! 🏆")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: PRIZES
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("## 📊 Distribución de premios")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Bote total", f"${st.session_state.total_pot:,.2f}")
        st.metric("Jugadores totales", len(st.session_state.players))

    with col2:
        buyin_count = len(st.session_state.players)
        rebuy_count = sum(p.get("rebuys", 0) for p in st.session_state.players)
        addon_count = sum(p.get("addons", 0) for p in st.session_state.players)
        st.metric("Buy-ins", f"{buyin_count} × ${st.session_state.buyin_amount}")
        st.metric("Recompras", f"{rebuy_count} × ${st.session_state.rebuy_amount}")
        st.metric("Add-ons", f"{addon_count} × ${st.session_state.addon_amount}")

    st.markdown("---")
    st.markdown("### 🏆 Estructura de premios")

    # Edit payout structure
    with st.expander("✏️ Editar estructura de premios"):
        n_places = st.number_input("Posiciones pagadas", min_value=1, max_value=10,
                                    value=len(st.session_state.payout_structure), step=1)

        while len(st.session_state.payout_structure) < n_places:
            st.session_state.payout_structure.append({"place": len(st.session_state.payout_structure) + 1, "pct": 0})
        while len(st.session_state.payout_structure) > n_places:
            st.session_state.payout_structure.pop()

        total_pct = 0
        for i, row in enumerate(st.session_state.payout_structure):
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"**{['🥇','🥈','🥉'][i] if i < 3 else f'#{i+1}' } lugar**")
            with c2:
                new_pct = st.number_input(
                    f"% para posición {i+1}",
                    min_value=0, max_value=100,
                    value=row["pct"], step=5,
                    key=f"pct_{i}",
                    label_visibility="collapsed"
                )
                st.session_state.payout_structure[i]["pct"] = new_pct
                total_pct += new_pct

        if total_pct != 100:
            st.warning(f"⚠️ Los porcentajes suman {total_pct}% (debe ser 100%)")
        else:
            st.success("✅ Porcentajes correctos")

    # Show prizes
    prizes = calculate_prizes()
    medals = ["🥇", "🥈", "🥉"]
    for i, pr in enumerate(prizes):
        medal = medals[i] if i < 3 else f"#{pr['place']}"
        st.markdown(f"""
        <div class="prize-row">
            <span class="prize-pos">{medal} {pr['place']}º lugar</span>
            <span class="prize-amount">${pr['amount']:,.2f} <span style="color: var(--gold-dark); font-size: 0.8rem;">({pr['pct']}%)</span></span>
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("## ⚙️ Configuración del torneo")

    if st.session_state.tournament_started:
        st.warning("⚠️ El torneo ya ha comenzado. Algunos cambios pueden no surtir efecto.")

    # General settings
    with st.expander("🏷️ Configuración general", expanded=True):
        st.session_state.tournament_name = st.text_input(
            "Nombre del torneo", value=st.session_state.tournament_name)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Buy-in**")
            st.session_state.buyin_amount = st.number_input(
                "Precio buy-in ($)", min_value=0, value=st.session_state.buyin_amount, step=5)
            st.session_state.buyin_chips = st.number_input(
                "Fichas buy-in", min_value=0, value=st.session_state.buyin_chips, step=500)
        with c2:
            st.markdown("**Recompra**")
            st.session_state.rebuy_amount = st.number_input(
                "Precio recompra ($)", min_value=0, value=st.session_state.rebuy_amount, step=5)
            st.session_state.rebuy_chips = st.number_input(
                "Fichas recompra", min_value=0, value=st.session_state.rebuy_chips, step=500)
            st.session_state.rebuy_level_limit = st.number_input(
                "Hasta nivel (recompras)", min_value=1,
                max_value=len(st.session_state.blind_levels),
                value=st.session_state.rebuy_level_limit)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Add-on**")
            st.session_state.addon_amount = st.number_input(
                "Precio add-on ($)", min_value=0, value=st.session_state.addon_amount, step=5)
            st.session_state.addon_chips = st.number_input(
                "Fichas add-on", min_value=0, value=st.session_state.addon_chips, step=500)
            st.session_state.addon_level_limit = st.number_input(
                "Hasta nivel (add-ons)", min_value=1,
                max_value=len(st.session_state.blind_levels),
                value=st.session_state.addon_level_limit)

    # Blind structure
    with st.expander("🎲 Estructura de ciegas"):
        st.markdown("Edita o añade niveles de ciegas:")

        # Add level
        cola, colb, colc, cold, cole = st.columns([2, 2, 2, 2, 1])
        with cola:
            ns = st.number_input("SB", min_value=0, value=500, step=50, key="new_sb")
        with colb:
            nb = st.number_input("BB", min_value=0, value=1000, step=50, key="new_bb")
        with colc:
            na = st.number_input("Ante", min_value=0, value=100, step=25, key="new_ante")
        with cold:
            nm = st.number_input("Min", min_value=1, value=10, step=5, key="new_min")
        with cole:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕"):
                st.session_state.blind_levels.append({
                    "small": ns, "big": nb, "ante": na, "minutes": nm
                })
                log_event(f"➕ Nivel añadido: {ns}/{nb}")
                st.rerun()

        st.markdown("---")

        # Show / edit existing levels
        levels_to_delete = []
        for i, lv in enumerate(st.session_state.blind_levels):
            c1, c2, c3, c4, c5, c6 = st.columns([0.5, 2, 2, 2, 2, 1])
            with c1:
                active_marker = "▶" if i == st.session_state.current_level and st.session_state.tournament_started else f"{i+1}"
                st.markdown(f"<div style='padding-top:0.7rem; color: var(--gold); font-weight:700;'>{active_marker}</div>", unsafe_allow_html=True)
            with c2:
                lv["small"] = st.number_input("SB", value=lv["small"], step=25, key=f"sb_{i}", label_visibility="collapsed")
            with c3:
                lv["big"] = st.number_input("BB", value=lv["big"], step=25, key=f"bb_{i}", label_visibility="collapsed")
            with c4:
                lv["ante"] = st.number_input("Ante", value=lv["ante"], step=25, key=f"ante_{i}", label_visibility="collapsed")
            with c5:
                lv["minutes"] = st.number_input("Min", value=lv["minutes"], step=5, key=f"min_{i}", label_visibility="collapsed")
            with c6:
                if st.button("🗑", key=f"del_{i}"):
                    levels_to_delete.append(i)

        for idx in reversed(levels_to_delete):
            st.session_state.blind_levels.pop(idx)
            log_event(f"🗑 Nivel {idx+1} eliminado")
        if levels_to_delete:
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: EVENT LOG
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("## 📋 Registro de eventos")

    if not st.session_state.event_log:
        st.info("El registro está vacío. Los eventos del torneo aparecerán aquí.")
    else:
        if st.button("🗑 Limpiar registro"):
            st.session_state.event_log = []
            st.rerun()
        for entry in st.session_state.event_log:
            st.markdown(f"""
            <div style="
                background: #0d3320;
                border-left: 3px solid var(--gold-dark);
                padding: 0.4rem 0.8rem;
                margin-bottom: 0.3rem;
                border-radius: 0 6px 6px 0;
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85rem;
                color: var(--cream);
            ">{entry}</div>
            """, unsafe_allow_html=True)
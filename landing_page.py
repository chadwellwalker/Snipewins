import streamlit as st


LAUNCHED = False


st.set_page_config(
    page_title="SnipeWins",
    page_icon="SW",
    layout="wide",
    initial_sidebar_state="collapsed",
)


COLORS = {
    "bg": "#000000",
    "text": "#EAEAEA",
    "muted": "#8A8A8A",
    "accent": "#00B874",
    "panel": "#060606",
    "border": "#171717",
}


PRELAUNCH_PROOF = {
    "player": "Victor Wembanyama Prizm Silver",
    "market_value": 182,
    "price": 132,
    "edge": 27,
}

LIVE_CARDS = [
    {
        "player": "CJ Stroud Donruss Optic Holo",
        "market_value": 128,
        "price": 104,
        "edge": 19,
        "time_left": "11m",
    },
    {
        "player": "Anthony Edwards Select Courtside",
        "market_value": 214,
        "price": 191,
        "edge": 12,
        "time_left": "27m",
    },
    {
        "player": "Shohei Ohtani Bowman Chrome",
        "market_value": 356,
        "price": 292,
        "edge": 18,
        "time_left": "6m",
    },
    {
        "player": "Caitlin Clark Prizm Draft Picks",
        "market_value": 94,
        "price": 81,
        "edge": 16,
        "time_left": "18m",
    },
]


def inject_styles() -> None:
    st.markdown(
        f"""
        <style>
            :root {{
                --bg: {COLORS["bg"]};
                --text: {COLORS["text"]};
                --muted: {COLORS["muted"]};
                --accent: {COLORS["accent"]};
                --panel: {COLORS["panel"]};
                --border: {COLORS["border"]};
            }}

            .stApp {{
                background: var(--bg);
            }}

            html, body, [class*="css"] {{
                color: var(--text);
                font-family: "Arial", sans-serif;
            }}

            .block-container {{
                max-width: 1180px;
                padding-top: 1.5rem;
                padding-bottom: 4rem;
                padding-left: 2.5rem;
                padding-right: 2.5rem;
            }}

            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            [data-testid="stStatusWidget"],
            [data-testid="collapsedControl"] {{
                display: none;
            }}

            .sw-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding-bottom: 1.25rem;
                border-bottom: 1px solid var(--border);
                margin-bottom: 4rem;
            }}

            .sw-logo {{
                color: var(--text);
                font-size: 0.92rem;
                letter-spacing: 0.26rem;
                font-weight: 700;
            }}

            .sw-button {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 42px;
                padding: 0 1.15rem;
                background: var(--accent);
                color: #04110b;
                font-size: 0.82rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
                text-decoration: none;
                border: none;
            }}

            .sw-hero {{
                max-width: 760px;
                padding-bottom: 4.5rem;
            }}

            .sw-kicker {{
                color: var(--muted);
                font-size: 0.78rem;
                text-transform: uppercase;
                letter-spacing: 0.2rem;
                margin-bottom: 1.2rem;
            }}

            .sw-hero h1 {{
                color: var(--text);
                font-size: clamp(3rem, 7vw, 5.5rem);
                line-height: 0.96;
                font-weight: 700;
                letter-spacing: -0.08rem;
                margin: 0;
                text-transform: uppercase;
            }}

            .sw-subheadline {{
                color: var(--muted);
                font-size: 1.1rem;
                line-height: 1.6;
                max-width: 640px;
                margin-top: 1.5rem;
            }}

            .sw-section {{
                padding-top: 1.25rem;
                margin-top: 1.25rem;
            }}

            .sw-section-label {{
                color: var(--muted);
                font-size: 0.74rem;
                text-transform: uppercase;
                letter-spacing: 0.18rem;
                margin-bottom: 0.9rem;
            }}

            .sw-section-title {{
                color: var(--text);
                font-size: 2rem;
                line-height: 1.05;
                font-weight: 700;
                margin-bottom: 1.1rem;
                text-transform: uppercase;
            }}

            .sw-radar-card {{
                background: var(--panel);
                border: 1px solid var(--border);
                border-left: 1px solid var(--border);
                padding: 1.15rem 1.1rem 1rem;
                height: 100%;
            }}

            .sw-radar-card.edge {{
                border-left: 3px solid var(--accent);
            }}

            .sw-radar-top {{
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: 1rem;
            }}

            .sw-player {{
                color: var(--text);
                font-size: 1rem;
                line-height: 1.35;
                font-weight: 700;
                text-transform: uppercase;
            }}

            .sw-time {{
                color: var(--muted);
                font-size: 0.78rem;
                white-space: nowrap;
                text-transform: uppercase;
            }}

            .sw-metric-grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.8rem;
            }}

            .sw-metric {{
                border-top: 1px solid var(--border);
                padding-top: 0.75rem;
            }}

            .sw-metric-label {{
                color: var(--muted);
                font-size: 0.72rem;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
                margin-bottom: 0.35rem;
            }}

            .sw-metric-value {{
                color: var(--text);
                font-size: 1.05rem;
                font-weight: 700;
            }}

            .sw-metric-value.edge {{
                color: var(--accent);
            }}

            .sw-steps {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
            }}

            .sw-step,
            .sw-feature {{
                background: var(--panel);
                border: 1px solid var(--border);
                padding: 1.25rem;
                min-height: 158px;
            }}

            .sw-step-num {{
                color: var(--muted);
                font-size: 0.78rem;
                margin-bottom: 1rem;
                text-transform: uppercase;
                letter-spacing: 0.1rem;
            }}

            .sw-step-title,
            .sw-feature-title {{
                color: var(--text);
                font-size: 1.15rem;
                font-weight: 700;
                text-transform: uppercase;
                margin-bottom: 0.7rem;
            }}

            .sw-step-copy,
            .sw-feature-copy {{
                color: var(--muted);
                font-size: 0.96rem;
                line-height: 1.6;
            }}

            .sw-feature-grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
            }}

            .sw-cta-band {{
                margin-top: 4.5rem;
                padding-top: 1.5rem;
                border-top: 1px solid var(--border);
            }}

            .sw-cta-band h2 {{
                color: var(--text);
                font-size: clamp(2rem, 5vw, 3.2rem);
                line-height: 1;
                font-weight: 700;
                text-transform: uppercase;
                margin-bottom: 0.7rem;
            }}

            .sw-cta-band p {{
                color: var(--muted);
                max-width: 600px;
                line-height: 1.6;
                margin-bottom: 1.3rem;
            }}

            .stTextInput > div > div > input {{
                background: #050505;
                color: var(--text);
                border: 1px solid var(--border);
                min-height: 48px;
                border-radius: 0;
            }}

            .stTextInput label {{
                color: var(--muted);
                font-size: 0.78rem;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
            }}

            .stButton > button {{
                width: 100%;
                min-height: 48px;
                border-radius: 0;
                border: none;
                background: var(--accent);
                color: #04110b;
                font-size: 0.82rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
            }}

            .stButton > button:hover {{
                background: var(--accent);
                color: #04110b;
            }}

            .stButton > button:focus {{
                box-shadow: none;
                outline: none;
            }}

            .sw-status {{
                color: var(--muted);
                font-size: 0.84rem;
                padding-top: 0.65rem;
            }}

            @media (max-width: 900px) {{
                .block-container {{
                    padding-left: 1.25rem;
                    padding-right: 1.25rem;
                }}

                .sw-header {{
                    gap: 1rem;
                    flex-direction: column;
                    align-items: flex-start;
                }}

                .sw-steps,
                .sw-feature-grid,
                .sw-metric-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    action = "Sign Up" if LAUNCHED else "Get Access"
    st.markdown(
        f"""
        <div class="sw-header">
            <div class="sw-logo">SNIPEWINS</div>
            <a class="sw-button" href="#cta">{action}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_radar_card(data: dict) -> None:
    has_priority_edge = data.get("edge", 0) > 15
    time_left = data.get("time_left")
    time_markup = f'<div class="sw-time">{time_left} left</div>' if time_left else ""
    border_class = " edge" if has_priority_edge else ""
    st.markdown(
        f"""
        <div class="sw-radar-card{border_class}">
            <div class="sw-radar-top">
                <div class="sw-player">{data["player"]}</div>
                {time_markup}
            </div>
            <div class="sw-metric-grid">
                <div class="sw-metric">
                    <div class="sw-metric-label">MV</div>
                    <div class="sw-metric-value">${data["market_value"]}</div>
                </div>
                <div class="sw-metric">
                    <div class="sw-metric-label">Price</div>
                    <div class="sw-metric-value">${data["price"]}</div>
                </div>
                <div class="sw-metric">
                    <div class="sw-metric-label">Edge</div>
                    <div class="sw-metric-value edge">{data["edge"]}%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_waitlist_form() -> None:
    st.markdown('<div id="cta"></div>', unsafe_allow_html=True)
    email_col, button_col = st.columns([3.2, 1.2], gap="small")
    with email_col:
        email = st.text_input("Email", placeholder="Enter your email", label_visibility="collapsed")
    with button_col:
        joined = st.button("Join Waitlist", use_container_width=True)

    if joined:
        if email and "@" in email:
            st.markdown(
                '<div class="sw-status">You are on the list. We will reach out when access opens.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sw-status">Enter a valid email to join the waitlist.</div>',
                unsafe_allow_html=True,
            )


def render_prelaunch_page() -> None:
    st.markdown(
        """
        <section class="sw-hero">
            <div class="sw-kicker">Pre-Launch Access</div>
            <h1>Find Underpriced Cards Before Anyone Else</h1>
            <div class="sw-subheadline">
                SnipeWins scans listings, calculates true market value, and shows you exactly what to buy.
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    render_waitlist_form()

    st.markdown(
        """
        <section class="sw-section">
            <div class="sw-section-label">Visual Proof</div>
            <div class="sw-section-title">One Look. Instant Signal.</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    proof_col_1, proof_col_2 = st.columns([1.15, 0.85], gap="large")
    with proof_col_1:
        render_radar_card(PRELAUNCH_PROOF)
    with proof_col_2:
        st.markdown(
            """
            <div class="sw-step" style="min-height:100%;">
                <div class="sw-step-title">Built For Card Traders</div>
                <div class="sw-step-copy">
                    Every listing is turned into a decision. You see the expected market value, the current ask, and
                    the edge before the rest of the market catches up.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <section class="sw-section">
            <div class="sw-section-label">How It Works</div>
        </section>
        <div class="sw-steps">
            <div class="sw-step">
                <div class="sw-step-num">01</div>
                <div class="sw-step-title">Scan</div>
                <div class="sw-step-copy">Finds listings as they hit the market and filters out the noise.</div>
            </div>
            <div class="sw-step">
                <div class="sw-step-num">02</div>
                <div class="sw-step-title">Value</div>
                <div class="sw-step-copy">Calculates the true price using recent comps, grade context, and market behavior.</div>
            </div>
            <div class="sw-step">
                <div class="sw-step-num">03</div>
                <div class="sw-step-title">Execute</div>
                <div class="sw-step-copy">Shows what to bid so you can move fast while the spread is still there.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <section class="sw-cta-band">
            <h2>Get Early Access</h2>
            <p>Join the first group using SnipeWins to spot profitable card buys before the market reprices them.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    render_waitlist_form()


def render_postlaunch_page() -> None:
    st.markdown(
        """
        <section class="sw-hero">
            <div class="sw-kicker">Live Buying Platform</div>
            <h1>Stop Guessing. Start Buying With Edge.</h1>
            <div class="sw-subheadline">
                SnipeWins shows you exactly which cards are underpriced and how much to bid.
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div id="cta"></div>', unsafe_allow_html=True)
    st.button("Start Sniping", use_container_width=False)

    st.markdown(
        """
        <section class="sw-section">
            <div class="sw-section-label">Live Product Feel</div>
            <div class="sw-section-title">Radar Board</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    card_columns = st.columns(len(LIVE_CARDS), gap="small")
    for column, card_data in zip(card_columns, LIVE_CARDS):
        with column:
            render_radar_card(card_data)

    st.markdown(
        """
        <section class="sw-section">
            <div class="sw-section-label">Features</div>
        </section>
        <div class="sw-feature-grid">
            <div class="sw-feature">
                <div class="sw-feature-title">Market Value Engine</div>
                <div class="sw-feature-copy">Turns comps into a clean market number so you can see real price dislocation fast.</div>
            </div>
            <div class="sw-feature">
                <div class="sw-feature-title">Steals</div>
                <div class="sw-feature-copy">Buy-it-now listings priced below market value — surfaced and ranked so the best spreads float to the top.</div>
            </div>
            <div class="sw-feature">
                <div class="sw-feature-title">Sniper Queue</div>
                <div class="sw-feature-copy">Organizes your best opportunities into an execution list so no edge gets missed.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <section class="sw-cta-band">
            <h2>Create Free Account</h2>
            <p>Open the platform, scan the board, and start buying cards with a measurable edge.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.button("Create Free Account", use_container_width=False)


def main() -> None:
    inject_styles()
    render_header()
    if LAUNCHED:
        render_postlaunch_page()
    else:
        render_prelaunch_page()


if __name__ == "__main__":
    main()

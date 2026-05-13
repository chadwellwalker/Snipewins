import React from "react";

const featuredCardImage = "/justin-jefferson-zebra-psa9.jpg";

const heroChips = [
  "Buy Signals",
  "Edge Detected",
  "Market Value",
  "Live Opportunities",
];

const whySignup = [
  {
    title: "See better opportunities",
    body: "Spot listings worth your attention before they get buried or bought.",
  },
  {
    title: "Read value faster",
    body: "Get tighter pricing context without grinding through messy comp work.",
  },
  {
    title: "Buy with conviction",
    body: "Move faster when the edge is real and skip the listings that are not.",
  },
];

const problems = [
  "Noisy search results bury the cards that actually deserve attention.",
  "Weak comps create bad entries and false confidence around price.",
  "The best opportunities disappear while most buyers are still hesitating.",
  "Too much time gets burned filtering noise instead of acting on value.",
];

const features = [
  {
    title: "Steals",
    body: "Buy-it-now listings priced under market value — surfaced before the market catches up.",
  },
  {
    title: "Market Value Engine",
    body: "Frame price instantly with sharper value context around every target card.",
  },
  {
    title: "Comp Intelligence",
    body: "Cut through messy sold data and focus on the comps that actually matter.",
  },
  {
    title: "Player Targeting",
    body: "Track the names, sets, and angles you care about without hunting manually.",
  },
  {
    title: "Snipe Workflow",
    body: "Move from search to decision with a workflow built for speed and discipline.",
  },
  {
    title: "Decision Support",
    body: "Know when to press, pass, or bid with more conviction and less hesitation.",
  },
];

const steps = [
  {
    number: "01",
    title: "Scan the market",
    body: "Watch active inventory with structure instead of refreshing blind.",
  },
  {
    number: "02",
    title: "Spot real value",
    body: "Read cleaner pricing context before the listing gets away.",
  },
  {
    number: "03",
    title: "Buy with conviction",
    body: "Act fast when the edge is there and stay disciplined when it is not.",
  },
];

const audiences = [
  "Flippers chasing clean margins",
  "Collectors building with discipline",
  "Breakers and modern buyers moving fast",
  "Anyone serious about buying smarter",
];

function SectionEyebrow({ children }) {
  return (
    <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-zinc-300">
      <span className="h-1.5 w-1.5 rounded-full bg-lime-400 shadow-[0_0_18px_rgba(163,230,53,0.75)]" />
      {children}
    </div>
  );
}

function ButtonPrimary({ children, href }) {
  const Tag = href ? "a" : "button";

  return (
    <Tag
      href={href}
      type={href ? undefined : "button"}
      className="inline-flex items-center justify-center rounded-full border border-lime-400/60 bg-lime-400 px-5 py-3 text-sm font-semibold text-black transition duration-200 hover:bg-lime-300"
    >
      {children}
    </Tag>
  );
}

function ButtonSecondary({ children, href }) {
  const Tag = href ? "a" : "button";

  return (
    <Tag
      href={href}
      type={href ? undefined : "button"}
      className="inline-flex items-center justify-center rounded-full border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white transition duration-200 hover:border-white/30 hover:bg-white/10"
    >
      {children}
    </Tag>
  );
}

function GridCard({ title, body, children, className = "" }) {
  return (
    <div
      className={`group overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.03] p-6 shadow-[0_18px_80px_rgba(0,0,0,0.45)] backdrop-blur-sm transition duration-300 hover:border-lime-400/25 hover:bg-white/[0.05] ${className}`}
    >
      {children}
      <h3 className="mt-5 text-xl font-semibold tracking-tight text-white">{title}</h3>
      <p className="mt-3 max-w-sm text-sm leading-6 text-zinc-400">{body}</p>
    </div>
  );
}

function FeatureIcon({ index }) {
  const iconStyles = [
    "from-lime-300/80 to-lime-500/20",
    "from-white/90 to-lime-400/20",
    "from-lime-200/70 to-white/10",
    "from-lime-400/70 to-transparent",
    "from-white/70 to-lime-400/25",
    "from-lime-300/75 to-lime-300/10",
  ];

  return (
    <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-black/40">
      <div className={`h-6 w-6 rounded-full bg-gradient-to-br ${iconStyles[index % iconStyles.length]}`} />
    </div>
  );
}

function SidebarOpportunity({ name, status, meta }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-white/[0.025] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-lg font-semibold tracking-[-0.03em] text-white">{name}</p>
          <p className="mt-2 text-sm text-zinc-500">{meta}</p>
        </div>
        <span className="shrink-0 pt-1 text-sm font-semibold uppercase tracking-[0.18em] text-lime-300">
          {status}
        </span>
      </div>
    </div>
  );
}

function MetricRow({ label, value, muted = false }) {
  return (
    <div
      className={`flex items-center justify-between rounded-[18px] border px-4 py-3 ${
        muted ? "border-white/5 bg-white/[0.01]" : "border-white/10 bg-white/[0.025]"
      }`}
    >
      <span className={`text-sm ${muted ? "text-zinc-500" : "text-zinc-400"}`}>{label}</span>
      <span className={`text-xl font-semibold tracking-[-0.03em] ${muted ? "text-zinc-300" : "text-white"}`}>
        {value}
      </span>
    </div>
  );
}

function ProductPreview() {
  return (
    <div className="mx-auto w-full min-w-0 max-w-[728px] rounded-[38px] border border-white/10 bg-[#0a0a0c]/95 p-5 shadow-[0_30px_170px_rgba(0,0,0,0.72)]">
      <div className="rounded-[32px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.015))] p-5">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-[0.34em] text-zinc-500">SNIPEWINS CONSOLE</div>
            <div className="mt-3 text-[2rem] font-semibold tracking-[-0.05em] text-white">Steals</div>
          </div>
          <div className="shrink-0 rounded-full border border-lime-400/30 bg-lime-400/10 px-5 py-2 text-sm font-semibold text-lime-300">
            Edge Active
          </div>
        </div>

        <div className="mt-6 grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="min-w-0 overflow-hidden rounded-[30px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.015))] p-6">
            <p className="text-xs uppercase tracking-[0.34em] text-zinc-500">LIVE OPPORTUNITY</p>

            <div className="mt-5 grid min-w-0 grid-cols-1 items-start gap-5 overflow-hidden lg:grid-cols-[132px_minmax(240px,1fr)_180px]">
              <div className="flex justify-center lg:block lg:w-[132px] lg:shrink-0">
                <div className="aspect-[5/7] w-[132px] max-w-full overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/90">
                  <img
                    src={featuredCardImage}
                    alt="2021 Panini Select Justin Jefferson Zebra PSA 9"
                    className="h-full w-full object-cover object-center"
                  />
                </div>
              </div>

              <div className="min-w-0 w-full max-w-full">
                <div className="min-w-0 space-y-0.5">
                  <p className="text-base font-semibold leading-snug tracking-[-0.03em] text-white lg:text-[1.0625rem]">
                    2021 Panini Select
                  </p>
                  <p className="text-base font-semibold leading-snug tracking-[-0.03em] text-white lg:text-[1.0625rem]">
                    Justin Jefferson
                  </p>
                  <p className="text-base font-semibold leading-snug tracking-[-0.03em] text-white lg:text-[1.0625rem]">
                    Zebra PSA 9
                  </p>
                </div>
                <div className="mt-5 flex w-full min-w-0 flex-col gap-3">
                  <MetricRow label="Auction ends" value="11m 27s" />
                  <MetricRow label="Comp quality" value="Strong" />
                  <MetricRow label="Volume trend" value="Rising" muted />
                </div>
              </div>

              <div className="flex w-full min-w-0 flex-col gap-4 lg:w-[180px] lg:shrink-0">
                <span className="inline-flex w-fit rounded-[22px] border border-lime-300/20 bg-lime-400/12 px-3 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-lime-300">
                  STRONG BUY
                </span>
                <div className="w-full rounded-[24px] border border-lime-400/18 bg-[linear-gradient(180deg,rgba(163,230,53,0.12),rgba(163,230,53,0.05))] p-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-lime-300/80">VALUE READ</p>
                  <p className="mt-2 text-xl font-semibold leading-tight tracking-[-0.05em] text-white lg:text-[1.625rem]">
                    $39 <span className="text-zinc-400">&rarr;</span> $78
                  </p>
                  <p className="mt-2 text-sm font-semibold uppercase tracking-[0.12em] text-lime-300">+100% edge</p>
                  <p className="mt-3 text-sm font-medium text-zinc-200">86% confidence</p>
                </div>
              </div>
            </div>
          </div>

          <div className="min-w-0 rounded-[30px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-5">
            <div className="text-xs uppercase tracking-[0.34em] text-zinc-500">LIVE OPPORTUNITIES</div>
            <div className="mt-5 flex flex-col gap-4">
              <SidebarOpportunity name="Mahomes Downtown PSA 9" status="WATCH" meta="#1 signal" />
              <SidebarOpportunity name="Wemby Silver Raw" status="REVIEW" meta="#2 signal queue" />
              <SidebarOpportunity name="Ohtani Auto /25" status="HOT" meta="#3 signal queue" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SnipeWinsLandingPage() {
  return (
    <main
      id="top"
      className="min-h-screen bg-[#050505] bg-[radial-gradient(ellipse_120%_80%_at_50%_-30%,rgba(255,255,255,0.07),transparent_50%),radial-gradient(ellipse_50%_40%_at_15%_10%,rgba(163,230,53,0.08),transparent_45%),linear-gradient(180deg,#050505_0%,#070709_38%,#050505_100%)] text-white antialiased"
    >
      <div className="isolate">
        <section className="mx-auto max-w-7xl border-t border-white/10 px-6 pb-20 pt-6 sm:px-8 lg:px-10 lg:pb-24">
          <header className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] text-sm font-semibold tracking-[0.3em] text-white">
                SW
              </div>
              <div>
                <div className="text-sm font-semibold tracking-[0.24em] text-white">SNIPEWINS</div>
                <div className="text-xs uppercase tracking-[0.22em] text-zinc-500">Buyer intelligence platform</div>
              </div>
            </div>

            <div className="hidden items-center gap-3 md:flex">
              <a href="#how-it-works" className="text-sm text-zinc-400 transition hover:text-white">
                How it works
              </a>
              <a href="#features" className="text-sm text-zinc-400 transition hover:text-white">
                Features
              </a>
              <ButtonPrimary href="#waitlist">Get Early Access</ButtonPrimary>
            </div>
          </header>

          <div className="grid items-start gap-16 pt-14 lg:grid-cols-[0.92fr_1.08fr] lg:pt-20">
            <div className="max-w-2xl min-w-0">
              <SectionEyebrow>PRELAUNCH ACCESS</SectionEyebrow>
              <h1 className="max-w-xl text-5xl font-semibold tracking-[-0.06em] text-white sm:text-6xl lg:text-7xl">
                Find underpriced cards before the market does.
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-zinc-300 sm:text-xl">
                SnipeWins helps serious buyers spot real eBay opportunities, estimate value faster, and buy with more
                conviction without drowning in bad comps and weak listings.
              </p>
              <p className="mt-4 text-sm font-medium tracking-[0.01em] text-zinc-200">
                Good cards don&apos;t sit. Neither should you.
              </p>

              <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                <ButtonPrimary href="#waitlist">Get Early Access</ButtonPrimary>
                <ButtonSecondary href="#how-it-works">See the Edge</ButtonSecondary>
              </div>
              <p className="mt-4 text-sm text-zinc-400">Limited rollout. Early users get the edge first.</p>

              <div className="mt-6 flex flex-wrap gap-3">
                {heroChips.map((item) => (
                  <div
                    key={item}
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium uppercase tracking-[0.18em] text-zinc-300"
                  >
                    {item}
                  </div>
                ))}
              </div>

              <div className="mt-5 inline-flex items-center rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-300">
                Sharper signals. Faster reads. Better buys.
              </div>

              <div className="mt-7 grid gap-3 sm:grid-cols-3">
                {whySignup.map((item) => (
                  <div
                    key={item.title}
                    className="rounded-[22px] border border-white/10 bg-white/[0.03] px-4 py-4 shadow-[0_14px_50px_rgba(0,0,0,0.25)]"
                  >
                    <div className="text-sm font-semibold text-white">{item.title}</div>
                    <p className="mt-2 text-sm leading-6 text-zinc-400">{item.body}</p>
                  </div>
                ))}
              </div>

              <p className="mt-6 text-sm text-zinc-500">
                Built for flippers, collectors, and modern buyers who want better entries, not more noise.
              </p>
            </div>

            <div className="min-w-0 justify-self-end lg:justify-self-auto">
              <ProductPreview />
            </div>
          </div>
        </section>

        <section className="border-t border-white/8">
          <div className="mx-auto grid max-w-7xl gap-10 px-6 py-20 sm:px-8 lg:grid-cols-[0.78fr_1.22fr] lg:px-10">
            <div>
              <SectionEyebrow>Problem</SectionEyebrow>
              <h2 className="max-w-md text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
                Bad comps cost money. Slow decisions cost cards.
              </h2>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {problems.map((problem) => (
                <div
                  key={problem}
                  className="rounded-[24px] border border-white/8 bg-white/[0.03] p-5 text-sm leading-7 text-zinc-300 shadow-[0_14px_60px_rgba(0,0,0,0.22)]"
                >
                  {problem}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-white/8">
          <div className="mx-auto grid max-w-7xl gap-12 px-6 py-20 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:px-10">
            <div>
              <SectionEyebrow>Solution</SectionEyebrow>
              <h2 className="max-w-lg text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
                SnipeWins turns chaotic browsing into a buying system.
              </h2>
            </div>

            <div className="rounded-[30px] border border-white/10 bg-white/[0.03] p-8 shadow-[0_20px_90px_rgba(0,0,0,0.35)]">
              <p className="max-w-2xl text-lg leading-8 text-zinc-300">
                It brings live opportunities, cleaner value context, and stronger buy signals into one tighter workflow.
              </p>
              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {[
                  "See real opportunities faster",
                  "Read market value with less friction",
                  "Cut through noisy comps",
                  "Make sharper decisions under pressure",
                ].map((item) => (
                  <div key={item} className="rounded-2xl border border-white/8 bg-black/30 px-4 py-4 text-sm text-zinc-200">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="border-t border-white/8">
          <div className="mx-auto max-w-7xl px-6 py-20 sm:px-8 lg:px-10">
            <SectionEyebrow>Feature Set</SectionEyebrow>
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="max-w-2xl text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
                  Built for buyers who want better entries, not more noise.
                </h2>
              </div>
              <p className="max-w-xl text-sm leading-7 text-zinc-500">
                Every surface is designed to shorten the distance between a listing and a confident decision.
              </p>
            </div>

            <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {features.map((feature, index) => (
                <GridCard key={feature.title} title={feature.title} body={feature.body}>
                  <FeatureIcon index={index} />
                </GridCard>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="border-t border-white/8">
          <div className="mx-auto max-w-7xl px-6 py-20 sm:px-8 lg:px-10">
            <SectionEyebrow>How It Works</SectionEyebrow>
            <div className="grid gap-6 lg:grid-cols-3">
              {steps.map((step) => (
                <div
                  key={step.number}
                  className="rounded-[28px] border border-white/10 bg-white/[0.03] p-7 shadow-[0_18px_80px_rgba(0,0,0,0.28)]"
                >
                  <div className="text-xs font-semibold uppercase tracking-[0.28em] text-lime-300">{step.number}</div>
                  <h3 className="mt-5 text-2xl font-semibold tracking-tight text-white">{step.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-zinc-400">{step.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-white/8">
          <div className="mx-auto grid max-w-7xl gap-10 px-6 py-20 sm:px-8 lg:grid-cols-[0.8fr_1.2fr] lg:px-10">
            <div>
              <SectionEyebrow>Who It&apos;s For</SectionEyebrow>
              <h2 className="max-w-md text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
                For buyers who take the market seriously.
              </h2>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {audiences.map((item, index) => (
                <div
                  key={item}
                  className="rounded-[24px] border border-white/8 bg-white/[0.03] p-5 transition hover:border-lime-400/25"
                >
                  <div className="text-xs font-semibold uppercase tracking-[0.25em] text-zinc-500">0{index + 1}</div>
                  <div className="mt-3 text-lg font-medium text-white">{item}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="waitlist" className="border-t border-white/8">
          <div className="mx-auto max-w-5xl px-6 py-20 sm:px-8 lg:px-10">
            <div className="overflow-hidden rounded-[34px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-8 shadow-[0_24px_120px_rgba(0,0,0,0.45)] sm:p-10">
              <SectionEyebrow>Waitlist</SectionEyebrow>
              <div className="grid gap-10 lg:grid-cols-[1fr_0.92fr] lg:items-end">
                <div>
                  <h2 className="max-w-xl text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
                    Get in before the edge gets crowded.
                  </h2>
                  <p className="mt-4 max-w-xl text-base leading-7 text-zinc-400">
                    Join the waitlist for first access to SnipeWins and start buying with better signals, tighter reads,
                    and more conviction.
                  </p>
                </div>

                <form className="rounded-[28px] border border-white/10 bg-black/30 p-4">
                  <label htmlFor="email" className="mb-3 block text-xs font-semibold uppercase tracking-[0.24em] text-zinc-500">
                    Email
                  </label>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      className="h-12 flex-1 rounded-full border border-white/10 bg-white/[0.04] px-4 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-lime-400/50"
                    />
                    <button
                      type="submit"
                      className="inline-flex h-12 items-center justify-center rounded-full border border-lime-400/60 bg-lime-400 px-5 text-sm font-semibold text-black transition duration-200 hover:bg-lime-300"
                    >
                      Get Early Access
                    </button>
                  </div>
                  <p className="mt-3 text-xs leading-6 text-zinc-500">Early access will roll out in limited waves.</p>
                </form>
              </div>
            </div>
          </div>
        </section>

        <footer className="border-t border-white/8">
          <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8 text-sm text-zinc-500 sm:px-8 lg:flex-row lg:items-center lg:justify-between lg:px-10">
            <div>
              <div className="font-semibold tracking-[0.24em] text-white">SNIPEWINS</div>
              <p className="mt-2">Sharper reads for buyers who want better cards and better entries.</p>
            </div>
            <div className="flex gap-5">
              <a href="#features" className="transition hover:text-white">
                Features
              </a>
              <a href="#how-it-works" className="transition hover:text-white">
                How it works
              </a>
              <a href="#waitlist" className="transition hover:text-white">
                Waitlist
              </a>
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}

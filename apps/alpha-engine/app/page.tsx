export default function HomePage() {
  return (
    <main>

      {/* ── S1: Hero ─────────────────────────────────────── */}
      <section className="ae-hero" id="top">
        <div className="ae-hero-grid-overlay" aria-hidden="true" />

        <div className="ae-hero-inner">

          {/* ── Left Column: Copy ── */}
          <div className="ae-hero-copy">
            <span className="ae-kicker">AI-Native Growth System</span>

            <h1 className="ae-headline ae-headline-lg">
              Grow the Customers You&nbsp;Have.<br />
              Find the Customers You&nbsp;Need.
            </h1>

            <p className="ae-subhead">
              AlphaEngine connects product, service, marketing, and media
              into one customer memory system&mdash;so teams can increase
              engagement, retention, expansion, and acquisition from a
              single growth engine.
            </p>

            <div className="ae-cta-row">
              <a href="#pilot" className="ae-cta-primary">Request a Pilot</a>
              <a href="#how-it-works" className="ae-cta-secondary">See How It Works</a>
            </div>

            <div className="ae-hero-support">
              <span>Grow existing customer value</span>
              <span className="ae-hero-support-dot" aria-hidden="true" />
              <span>Build new customer supply</span>
              <span className="ae-hero-support-dot" aria-hidden="true" />
              <span>Prove what works</span>
            </div>
          </div>

          {/* ── Right Column: System Diagram ── */}
          <div className="ae-hero-diagram" aria-label="AlphaEngine system diagram">

            {/* Input tier */}
            <div className="ae-diagram-tier ae-diagram-inputs">
              <span className="ae-diagram-tier-label">Inputs</span>
              <div className="ae-diagram-node-row">
                {['Product', 'Service', 'Marketing', 'Sales', 'Research'].map(
                  (label) => (
                    <div key={label} className="ae-diagram-node ae-diagram-node--sm">
                      <span className="ae-diagram-node-label">{label}</span>
                    </div>
                  )
                )}
              </div>
            </div>

            {/* Connector: inputs → hub */}
            <div className="ae-diagram-connector ae-diagram-connector--fan" aria-hidden="true">
              <div className="ae-diagram-line" />
              <div className="ae-diagram-line" />
              <div className="ae-diagram-line" />
            </div>

            {/* Central hub */}
            <div className="ae-diagram-tier ae-diagram-hub">
              <div className="ae-diagram-node ae-diagram-node--hub">
                <span className="ae-diagram-node-icon" aria-hidden="true">&#x25C9;</span>
                <span className="ae-diagram-node-label">Customer Memory</span>
              </div>
            </div>

            {/* Connector: hub → processing */}
            <div className="ae-diagram-connector ae-diagram-connector--single" aria-hidden="true">
              <div className="ae-diagram-line" />
            </div>

            {/* Processing tier */}
            <div className="ae-diagram-tier ae-diagram-processing">
              <div className="ae-diagram-node ae-diagram-node--mid">
                <span className="ae-diagram-node-label">AI Decision Layer</span>
              </div>
            </div>

            {/* Connector: processing → outputs */}
            <div className="ae-diagram-connector ae-diagram-connector--fan" aria-hidden="true">
              <div className="ae-diagram-line" />
              <div className="ae-diagram-line" />
              <div className="ae-diagram-line" />
            </div>

            {/* Output tier */}
            <div className="ae-diagram-tier ae-diagram-outputs">
              <span className="ae-diagram-tier-label">Outputs</span>
              <div className="ae-diagram-node-row">
                {['Retention', 'Expansion', 'Advocacy', 'Targeting', 'Acquisition'].map(
                  (label) => (
                    <div key={label} className="ae-diagram-node ae-diagram-node--sm">
                      <span className="ae-diagram-node-label">{label}</span>
                    </div>
                  )
                )}
              </div>
            </div>

          </div>
        </div>
      </section>


      {/* ── S2: The Broken Customer Journey ──────────────── */}
      <section className="ae-section ae-section-alt" id="how-it-works">
        <div className="ae-container">
          <span className="ae-kicker">The Problem</span>
          <h2 className="ae-headline">
            One Customer. Seven Touchpoints.<br />Zero Coordination.
          </h2>
          <p className="ae-subhead">
            Your customer experiences one relationship. Your company operates
            through disconnected systems. Here&rsquo;s what that actually looks like.
          </p>

          <div className="ae-timeline">
            <div className="ae-timeline-day">
              <span className="ae-day-label">Mon</span>
              <p className="ae-day-text">
                She hits a <strong>bug in the product</strong>. She reports it
                through in-app feedback. The product team logs it in their backlog.
                Marketing doesn&rsquo;t know. Support doesn&rsquo;t know. CRM
                doesn&rsquo;t know.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Tue</span>
              <p className="ae-day-text">
                She <strong>calls support</strong> about the same bug. The agent
                has no record of her in-app report. She explains it from scratch.
                Support logs a ticket in their system. It doesn&rsquo;t connect to
                the product backlog or her CRM record.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Wed</span>
              <p className="ae-day-text">
                Marketing sends her an <strong>upsell email</strong> for the
                premium tier&mdash;the one that includes the feature that&rsquo;s
                currently broken for her. She screenshots it and sends it to a
                colleague with a frustrated comment.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Thu</span>
              <p className="ae-day-text">
                She receives a <strong>satisfaction survey</strong>. She rates the
                company 3 out of 10. The research team logs the score. Nobody
                connects it to the open support ticket, the broken feature, or
                the badly timed upsell.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Fri</span>
              <p className="ae-day-text">
                An automated <strong>review request</strong> hits her inbox.
                She&rsquo;s still waiting on her support ticket. She ignores it.
                Her engagement score drops, but nobody knows why.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Sat</span>
              <p className="ae-day-text">
                She sees a <strong>retargeting ad</strong> for the product she
                already owns. She&rsquo;s paying for it. She&rsquo;s frustrated
                with it. Now she&rsquo;s being sold it again.
              </p>
            </div>
            <div className="ae-timeline-day">
              <span className="ae-day-label">Sun</span>
              <p className="ae-day-text">
                A renewal notice arrives with a <strong>generic retention
                offer</strong>&mdash;a discount on something she doesn&rsquo;t
                need. The cancellation process is easier than the support process was.
              </p>
            </div>
          </div>

          <div className="ae-timeline-result">
            <p>
              Customer lost. $4,200 lifetime value gone. Reacquisition cost: ~$380.
              No system connected the signals.
            </p>
          </div>

          <div className="ae-timeline-counter">
            <p>
              <strong>Now imagine the same week&mdash;with shared memory.</strong>{' '}
              Support knows about the bug report before she calls. Marketing
              suppresses the upsell. The survey triggers a service recovery
              workflow. The review request is held. The retargeting ad is paused.
              The renewal offer is personalized to her actual situation. She stays.
              She upgrades three months later.
            </p>
          </div>

          <p className="ae-punchline">
            That&rsquo;s the difference between channel automation and relationship intelligence.
          </p>
        </div>
      </section>

      {/* ── S3: Part A — Headline ────────────────────────── */}
      <section className="ae-section ae-section-dark">
        <div className="ae-container">
          <span className="ae-kicker">Part A &mdash; The Relationship Engine</span>
          <h2 className="ae-headline">
            Grow the Customers You Already Have.
          </h2>
          <p className="ae-subhead">
            The bigger growth problem isn&rsquo;t acquisition. It&rsquo;s the
            value you&rsquo;re leaving inside your installed base&mdash;because
            your systems don&rsquo;t share memory.
          </p>
          <p className="ae-body" style={{ marginTop: 20 }}>
            Every company has the same structural gap: the customer experiences one
            relationship, but the business operates through disconnected product,
            marketing, service, sales, and research systems. That gap costs more
            than most leaders realize&mdash;in retention, pricing power, cross-sell,
            upsell, advocacy, and the real-time understanding needed to act when it
            matters.
          </p>
          <p className="ae-body" style={{ marginTop: 12 }}>
            AlphaEngine&rsquo;s Relationship Engine closes that gap. Not with
            another dashboard. Not with another integration layer. With shared
            customer memory that every team and channel reads from&mdash;so every
            action builds on the last one.
          </p>
        </div>
      </section>

      {/* ── S4: Part A — Company Problem ─────────────────── */}
      <section className="ae-section ae-section-alt">
        <div className="ae-container">
          <span className="ae-kicker">What Fragmentation Costs</span>
          <h2 className="ae-headline">
            Fragmentation Doesn&rsquo;t Just Frustrate Customers.<br />
            It Bleeds the Business.
          </h2>
          <p className="ae-subhead">
            When systems don&rsquo;t share context, companies miss the signals that
            drive retention, expansion, and long-term value.
          </p>

          <div className="ae-problem-grid">
            <div className="ae-problem-card">
              <h4>Retention</h4>
              <p>
                Recoverable customers leave because no system connects the warning
                signs. A support ticket, a declining engagement score, and a negative
                survey sit in three different tools. By the time someone notices,
                the customer is gone.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Revenue Expansion</h4>
              <p>
                Cross-sell and upsell windows open and close invisibly. A customer
                who just expanded product usage is ready for the next tier&mdash;but
                sales doesn&rsquo;t know, because adoption signals live in product
                analytics, not the CRM.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Pricing Power</h4>
              <p>
                Willingness to pay changes with the relationship. A customer getting
                high value is receptive to premium pricing. One experiencing friction
                is not. Without real-time context, pricing conversations happen blind.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Advocacy</h4>
              <p>
                Your most satisfied customers are your best growth channel&mdash;but
                you can&rsquo;t activate them if you don&rsquo;t know who they are,
                when they&rsquo;re receptive, or what made them successful.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Media Efficiency</h4>
              <p>
                You&rsquo;re paying to reacquire customers you already have.
                You&rsquo;re retargeting people who are frustrated. Without customer
                memory informing media, acquisition budgets subsidize retention
                failures.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Real-Time Understanding</h4>
              <p>
                The most important question isn&rsquo;t &ldquo;what
                happened?&rdquo; It&rsquo;s &ldquo;what is happening right
                now&mdash;and what should we do about it?&rdquo; Fragmented systems
                cannot answer that.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S5: Part A — Marketecture ────────────────────── */}
      <section className="ae-section ae-section-dark">
        <div className="ae-container">
          <span className="ae-kicker">The Architecture</span>
          <h2 className="ae-headline">
            The AlphaEngine Relationship Engine.
          </h2>
          <p className="ae-subhead">
            Shared memory. Contextual intelligence. Coordinated action. Measured truth.
          </p>
          <p className="ae-body" style={{ marginTop: 12 }}>
            Six layers that work together to turn disconnected customer touchpoints
            into a unified growth system.
          </p>

          <div className="ae-layers">
            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">01</span>
                <span className="ae-layer-title">Customer Connect</span>
              </div>
              <p className="ae-layer-subtitle">The routing and signal-ingestion layer.</p>
              <p className="ae-layer-body">
                Wires together the systems that already touch your
                customers&mdash;product events, marketing engagement, service
                interactions, sales and CS activity, surveys and research, billing
                and renewal signals, media and audience data. One live relationship
                stream that every downstream layer reads from.
              </p>
              <div className="ae-layer-tags">
                <span className="ae-layer-tag">Product</span>
                <span className="ae-layer-tag">Marketing</span>
                <span className="ae-layer-tag">Service</span>
                <span className="ae-layer-tag">Sales / CS</span>
                <span className="ae-layer-tag">Research</span>
                <span className="ae-layer-tag">Billing</span>
                <span className="ae-layer-tag">Media</span>
              </div>
            </div>

            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">02</span>
                <span className="ae-layer-title">Contextual Memory Banks</span>
              </div>
              <p className="ae-layer-subtitle">
                Not one generic customer profile. Purpose-built memory systems.
              </p>
              <p className="ae-layer-body">
                Six memory banks that preserve the right context for the right
                decisions. Each is continuously updated. Every team and channel reads
                from the same set.
              </p>
              <div className="ae-layer-tags">
                <span className="ae-layer-tag">Product Memory</span>
                <span className="ae-layer-tag">Service Memory</span>
                <span className="ae-layer-tag">Engagement Memory</span>
                <span className="ae-layer-tag">Commercial Memory</span>
                <span className="ae-layer-tag">Lifecycle Memory</span>
                <span className="ae-layer-tag">Relationship Memory</span>
              </div>
            </div>

            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">03</span>
                <span className="ae-layer-title">Relationship Intelligence Engine</span>
              </div>
              <p className="ae-layer-subtitle">The scoring and decision layer.</p>
              <p className="ae-layer-body">
                Turns contextual memory into actionable scores and recommendations.
                What is this customer worth today? What could they be worth? What
                should we do right now&mdash;and what should we not do?
              </p>
              <div className="ae-layer-tags">
                <span className="ae-layer-tag">Valuation</span>
                <span className="ae-layer-tag">Potential</span>
                <span className="ae-layer-tag">Next Best Action</span>
                <span className="ae-layer-tag">JTBD</span>
                <span className="ae-layer-tag">Receptivity</span>
                <span className="ae-layer-tag">Risk</span>
              </div>
            </div>

            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">04</span>
                <span className="ae-layer-title">AI Personalizer</span>
              </div>
              <p className="ae-layer-subtitle">
                Connected intelligence across the entire lifecycle.
              </p>
              <p className="ae-layer-body">
                Understands the customer across product, marketing, and
                service&mdash;at any point in the lifecycle&mdash;and determines not
                just what to say, but whether to say anything at all. This is the
                layer that prevents the Wednesday upsell email to the Monday bug
                reporter.
              </p>
            </div>

            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">05</span>
                <span className="ae-layer-title">Orchestration Layer</span>
              </div>
              <p className="ae-layer-subtitle">
                The right action, in the right channel, at the right time&mdash;or
                deliberate silence.
              </p>
              <p className="ae-layer-body">
                Activates decisions across every channel: email, in-product
                messaging, CS and support workflows, sales and renewal motions,
                survey follow-up, paid media suppression and exclusion, pricing
                triggers. Not about sending more messages. About coordinating the
                right ones.
              </p>
              <div className="ae-layer-tags">
                <span className="ae-layer-tag">Email</span>
                <span className="ae-layer-tag">In-Product</span>
                <span className="ae-layer-tag">CS / Support</span>
                <span className="ae-layer-tag">Sales</span>
                <span className="ae-layer-tag">Suppression</span>
                <span className="ae-layer-tag">Media</span>
                <span className="ae-layer-tag">Pricing</span>
              </div>
            </div>

            <div className="ae-layer">
              <div className="ae-layer-header">
                <span className="ae-layer-num">06</span>
                <span className="ae-layer-title">Truth Layer</span>
              </div>
              <p className="ae-layer-subtitle">
                Measure whether the relationship is getting healthier&mdash;not just
                whether the message was sent.
              </p>
              <p className="ae-layer-body">
                Optimizes for relationship health: engagement depth, satisfaction
                trajectory, retention, cross-sell and upsell conversion, advocacy
                activation, pricing power, and incremental revenue. Feeds back into
                the Intelligence Engine, making every decision smarter than the last.
              </p>
              <div className="ae-layer-tags">
                <span className="ae-layer-tag">Engagement</span>
                <span className="ae-layer-tag">Retention</span>
                <span className="ae-layer-tag">Expansion</span>
                <span className="ae-layer-tag">Advocacy</span>
                <span className="ae-layer-tag">Pricing Power</span>
                <span className="ae-layer-tag">Incremental Revenue</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── S6: Part A — Outcomes ─────────────────────────── */}
      <section className="ae-section ae-section-alt">
        <div className="ae-container">
          <span className="ae-kicker">Outcomes</span>
          <h2 className="ae-headline">
            What Changes When Your Systems Share Memory.
          </h2>
          <p className="ae-subhead">
            The Relationship Engine doesn&rsquo;t add another tool. It makes the
            tools you already have work as one system.
          </p>

          <div className="ae-outcome-list">
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Retention improves</strong> because at-risk signals are
                caught and acted on before they compound&mdash;not after the
                customer has already decided to leave.
              </p>
            </div>
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Expansion accelerates</strong> because adoption and
                readiness signals are visible to the teams that can act on
                them&mdash;when the window is open.
              </p>
            </div>
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Advocacy activates</strong> because the system identifies
                your most satisfied customers and engages them at the right moment.
              </p>
            </div>
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Pricing power increases</strong> because you understand
                what each customer values, what they&rsquo;re willing to pay, and
                when to have the conversation.
              </p>
            </div>
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Media waste drops</strong> because customer memory informs
                suppression, exclusion, and retargeting&mdash;so acquisition
                budgets stop subsidizing retention failures.
              </p>
            </div>
            <div className="ae-outcome">
              <div className="ae-outcome-dot" />
              <p>
                <strong>Decision speed increases</strong> because every team reads
                from the same relationship truth&mdash;no more reconciling
                conflicting reports from disconnected systems.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S7: The Bridge ───────────────────────────────── */}
      <section className="ae-bridge" id="bridge">
        <div className="ae-container">
          <span className="ae-kicker">The Connection</span>
          <h2 className="ae-headline">
            Your Best Customers Should Teach You<br />
            How to Find Your Next Best Customers.
          </h2>
          <div className="ae-divider-center" />
          <p className="ae-body">
            Most companies treat customer retention and customer acquisition as
            separate functions with separate data, separate teams, and separate
            strategies. That&rsquo;s a structural mistake.
          </p>
          <p className="ae-body" style={{ marginTop: 14 }}>
            The companies that deeply understand their best customers&mdash;what
            they value, what they pay, what made them successful&mdash;are the same
            companies that can model who to acquire next, identify the right
            problem statements, build creative that resonates, choose channels
            based on evidence, and measure what actually drove the outcome.
          </p>
          <p className="ae-bridge-emphasis">
            Customer memory is not just a retention tool. It&rsquo;s an acquisition
            strategy.
          </p>
        </div>
      </section>

      {/* ── S8: Part B — The Acquisition Problem ──────────── */}
      <section className="ae-section ae-section-alt">
        <div className="ae-container">
          <span className="ae-kicker">The Acquisition Problem</span>
          <h2 className="ae-headline">
            The Playbook That Built Your Pipeline<br />
            Is Running Out of Runway.
          </h2>
          <p className="ae-subhead">
            Search-led growth powered the last two decades of digital marketing.
            AI is rewriting how consumers discover, evaluate, and choose&mdash;and
            the old model can&rsquo;t keep up.
          </p>

          <div className="ae-problem-grid">
            <div className="ae-problem-card">
              <h4>Discovery Is Shifting</h4>
              <p>
                AI assistants, social feeds, and recommendation engines are replacing
                search as the front door. If your acquisition strategy starts and
                ends with SEO and SEM, your pipeline is increasingly dependent on a
                shrinking surface.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Targeting Is Blind</h4>
              <p>
                Most audience targeting is built on third-party signals and generic
                lookalikes&mdash;not on what you actually know about your best
                customers. You&rsquo;re spending to reach people who look like
                buyers, not people who behave like your best ones.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Creative Is Optimized for Clicks</h4>
              <p>
                Ad testing measures thumbstops and click-throughs, not whether the
                message actually moved someone. High-performing creative by platform
                metrics often has zero incremental impact on revenue.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>Measurement Is Broken</h4>
              <p>
                Last-click attribution tells you what happened last, not what
                actually caused the conversion. Campaigns that look like winners by
                proxy metrics are often the ones adding the least incremental value.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>No Memory Between Motions</h4>
              <p>
                Retention and acquisition run on separate data, separate teams, and
                separate budgets. You&rsquo;re paying to reacquire customers you
                already have&mdash;and ignoring the intelligence your installed base
                can provide about who to acquire next.
              </p>
            </div>
            <div className="ae-problem-card">
              <h4>CAC Is Rising, LTV Is Flat</h4>
              <p>
                When targeting, creative, and measurement are all disconnected from
                customer truth, the result is predictable: acquisition costs climb
                while the quality of new customers stagnates. The math stops working.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S9: Part B — Headline + Product Screenshot ──── */}
      <section className="ae-section ae-section-dark">
        <div className="ae-container-wide">
          <div className="ae-growth-engine-grid">
            <div className="ae-growth-engine-copy">
              <span className="ae-kicker">Part B &mdash; The Growth Engine</span>
              <h2 className="ae-headline">
                Create a Continuous Supply of New Customers.
              </h2>
              <p className="ae-subhead">
                The next generation of customer acquisition won&rsquo;t be built on
                better bidding. It will be built on deeper customer
                understanding&mdash;driving sharper targeting, stronger creative
                optimized for real human response, and rigorous measurement proving
                what actually drives incremental revenue.
              </p>
              <p className="ae-body" style={{ marginTop: 20 }}>
                AlphaEngine&rsquo;s Growth Engine connects your customer intelligence
                to every stage of acquisition. Your best customers become the
                blueprint&mdash;their behavior, value, and trajectory inform who to
                target, what to say, and how to measure whether it worked.
              </p>
            </div>
            <div className="ae-growth-engine-shot">
              <div className="ae-product-shot-frame">
                <img
                  src="/dashboard-preview.png"
                  alt="AlphaEngine Bio Optimizer — scene-by-scene timeline report with attention scoring and signal overlays"
                  width={1440}
                  height={900}
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── S9: Part B — Product Suite ───────────────────── */}
      <section className="ae-section ae-section-alt">
        <div className="ae-container">
          <span className="ae-kicker">The Product Suite</span>
          <h2 className="ae-headline">
            Three Capabilities. One Acquisition Flywheel.
          </h2>

          <div className="ae-products">
            <div className="ae-product">
              <h3 className="ae-product-name">AlphaEngine Targeting</h3>
              <p className="ae-product-tagline">
                Find higher-quality prospects by learning from your best customers.
              </p>
              <p className="ae-product-body">
                Uses your existing customer base&mdash;their value, behavior, and
                trajectory&mdash;to build higher-quality lookalike audiences and
                identify the prospects most likely to become your next best
                customers. Not generic lookalike modeling. Targeting informed by
                deep relationship intelligence.
              </p>
            </div>

            <div className="ae-product">
              <h3 className="ae-product-name">AlphaEngine Bio Optimizer</h3>
              <p className="ae-product-tagline">
                Optimize creative for real human impact&mdash;not just clicks.
              </p>
              <p className="ae-product-body">
                Enables creative teams to score and optimize ads based on attention
                and biological/behavioral response&mdash;measuring what the creative
                actually does to the viewer, not just whether they interacted with
                it.
              </p>
              <div className="ae-product-proof">
                <p>
                  36.8% view rate on winning creative&mdash;outperforming 24
                  competing short-form ads by 20% in 30-day testing.
                </p>
              </div>
            </div>

            <div className="ae-product">
              <h3 className="ae-product-name">AlphaEngine Attribution</h3>
              <p className="ae-product-tagline">
                Prove what actually works. Invest with confidence.
              </p>
              <p className="ae-product-body">
                Replaces proxy-based measurement with incrementality testing and
                geo-experimental design&mdash;showing the true causal impact of
                every channel, campaign, and creative variation. When you know what
                actually works, you can build a growth flywheel that compounds.
              </p>
              <div className="ae-product-proof">
                <p>
                  140&ndash;280% incremental ROAS via geo-experimental testing vs.
                  6.4% last-click attributed. Same campaigns. Opposite optimization
                  decisions.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── S10: Part B — Flywheel ───────────────────────── */}
      <section className="ae-section ae-section-dark">
        <div className="ae-container">
          <span className="ae-kicker">The Flywheel</span>
          <h2 className="ae-headline">Each Capability Makes the Others Stronger.</h2>

          <div className="ae-flywheel">
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&rarr;</span>
              <p>
                <strong>Better customer understanding</strong> (from the Relationship
                Engine) improves targeting precision
              </p>
            </div>
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&rarr;</span>
              <p>
                <strong>Better targeting</strong> improves media efficiency and
                reduces waste
              </p>
            </div>
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&rarr;</span>
              <p>
                <strong>Better creative</strong>&mdash;optimized for biological
                impact&mdash;improves engagement and conversion
              </p>
            </div>
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&rarr;</span>
              <p>
                <strong>Better measurement</strong> proves what&rsquo;s actually
                driving incremental revenue
              </p>
            </div>
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&rarr;</span>
              <p>
                <strong>Proven performance</strong> unlocks reinvestment in the
                channels and creative that work
              </p>
            </div>
            <div className="ae-flywheel-step">
              <span className="ae-flywheel-arrow">&#x21bb;</span>
              <p>
                <strong>Reinvestment compounds growth</strong>&mdash;sustainably.
                Each cycle produces better data, better decisions, and better results
                than the last.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S11: Proof + Results ──────────────────────────── */}
      <section className="ae-section ae-section-alt" id="results">
        <div className="ae-container-wide">
          <div className="ae-container">
            <span className="ae-kicker">Results</span>
            <h2 className="ae-headline">Results That Prove the System Works.</h2>
            <p className="ae-subhead">
              Real outcomes. Real measurement. No invented numbers.
            </p>
          </div>

          <div className="ae-proof-grid">
            <div className="ae-proof-card">
              <span className="ae-proof-context">Bio Optimizer</span>
              <span className="ae-proof-number">36.8%</span>
              <span className="ae-proof-label">View rate on winning creative</span>
              <p className="ae-proof-detail">
                Outperformed 24 competing short-form ads by 20% in 30-day testing period.
              </p>
            </div>
            <div className="ae-proof-card">
              <span className="ae-proof-context">Attribution</span>
              <span className="ae-proof-number">140&ndash;280%</span>
              <span className="ae-proof-label">Incremental ROAS</span>
              <p className="ae-proof-detail">
                Via geo-experimental testing vs. 6.4% last-click attributed. Same
                campaigns. Opposite optimization decisions.
              </p>
            </div>
            <div className="ae-proof-card">
              <span className="ae-proof-context">Full System</span>
              <span className="ae-proof-number">3.4&times;</span>
              <span className="ae-proof-label">Revenue growth</span>
              <p className="ae-proof-detail">
                From $1.1B to $3.8B without proportional budget increases. Brand
                awareness from 0% to 65%.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S12: Who It's For ────────────────────────────── */}
      <section className="ae-section ae-section-dark">
        <div className="ae-container-wide">
          <div className="ae-container">
            <span className="ae-kicker">Built For</span>
            <h2 className="ae-headline">
              Growth Leaders Who Own the Full Picture.
            </h2>
          </div>

          <div className="ae-roles-grid">
            <div className="ae-role-card">
              <h4 className="ae-role-title">CMO / Head of Growth</h4>
              <p>
                You own the number. AlphaEngine connects retention and acquisition
                into one growth strategy&mdash;with measurement you can trust.
              </p>
            </div>
            <div className="ae-role-card">
              <h4 className="ae-role-title">CRO / Revenue Leader</h4>
              <p>
                Expansion, pricing, and new revenue depend on understanding what
                customers actually need. AlphaEngine makes that understanding
                operational.
              </p>
            </div>
            <div className="ae-role-card">
              <h4 className="ae-role-title">Head of Product / CPO</h4>
              <p>
                Product usage is the strongest signal in the relationship.
                AlphaEngine connects product data to marketing, service, and
                sales&mdash;so product intelligence drives customer outcomes.
              </p>
            </div>
            <div className="ae-role-card">
              <h4 className="ae-role-title">VP Lifecycle / CRM</h4>
              <p>
                You know the journey should be coordinated. AlphaEngine gives you
                the shared memory and orchestration to make it real&mdash;across
                every team and channel.
              </p>
            </div>
            <div className="ae-role-card">
              <h4 className="ae-role-title">Customer Success / Support</h4>
              <p>
                Service interactions are the most honest signals in the customer
                relationship. AlphaEngine turns them into strategic intelligence
                instead of siloed tickets.
              </p>
            </div>
            <div className="ae-role-card">
              <h4 className="ae-role-title">CEO / PE Operating Partner</h4>
              <p>
                Customer growth is the board-level metric. AlphaEngine connects
                retention, expansion, and acquisition into one measurable growth
                engine&mdash;with proof of what&rsquo;s working.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── S13: Final CTA ───────────────────────────────── */}
      <section className="ae-final-cta" id="pilot">
        <div className="ae-container">
          <span className="ae-kicker">Get Started</span>
          <h2 className="ae-headline">
            See What AlphaEngine Can Do for Your Growth.
          </h2>
          <p className="ae-subhead">
            We run focused 30&ndash;60 day pilots designed to prove measurable
            impact on the metrics that matter to your business.
          </p>
          <div className="ae-cta-row">
            <a href="mailto:hello@alphaengine.ai" className="ae-cta-primary">
              Request a Pilot
            </a>
          </div>
          <p className="ae-contact-line">
            <a href="mailto:hello@alphaengine.ai">hello@alphaengine.ai</a>
            {' '}&middot;{' '}Los Angeles, CA
            {' '}&middot;{' '}We respond within one business day
          </p>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className="ae-footer">
        <p>&copy; {new Date().getFullYear()} AlphaEngine. All rights reserved.</p>
      </footer>
    </main>
  );
}

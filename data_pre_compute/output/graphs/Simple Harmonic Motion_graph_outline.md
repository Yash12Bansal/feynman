# Simple Harmonic Motion

## Simple Harmonic Motion

Simple harmonic motion (SHM) is a special type of oscillatory motion where a particle oscillates on a straight line with acceleration always directed towards a fixed point (center of oscillation) and proportional to displacement from that point. The defining equation is a = -ω²x, where ω² is a positive constant. This can also be expressed as F = -kx (Hooke's law), where k = mω² is the spring constant. The negative sign indicates the restoring nature of the force. SHM represents the most fundamental type of oscillatory motion in physics, appearing in systems from atomic vibrations to planetary motions. The motion is characterized by its sinusoidal nature, with displacement varying as x = A sin(ωt + δ), where A is amplitude, ω is angular frequency, and δ is phase constant. Energy oscillates between kinetic and potential forms while total mechanical energy remains constant in ideal SHM.


  ### Definition and Basic Concepts

  Simple harmonic motion is defined by the acceleration equation a = -ω²x, where acceleration is proportional to displacement but opposite in direction. This leads to the force equation F = -kx, where k = mω² is the force/spring constant. The motion occurs about an equilibrium position (center of oscillation) where the net force is zero. Key characteristics include: (1) Motion is periodic with regular time intervals, (2) Particle oscillates along a straight line, (3) Acceleration always points toward equilibrium, (4) Force is a linear restoring force. The restoring force brings the particle back to equilibrium, making SHM a stable oscillatory motion. Example: A 4N force at 5cm displacement gives spring constant k = F/x = 4N/(0.05m) = 80 N/m.


  ### Qualitative Nature of SHM

  Consider a mass m on a frictionless surface attached to a spring with constant k. When displaced to amplitude A and released, the motion exhibits key features: (1) Maximum speed occurs at equilibrium (x=0), (2) Zero speed at extreme positions (x=±A), (3) Acceleration maximum at extremes, zero at center, (4) Force varies linearly with displacement. Energy conservation shows that potential energy at extremes (½kA²) equals kinetic energy at center (½mv₀²), proving equal displacement on both sides. The particle oscillates between positions P and Q with OP = OQ = A (amplitude). This demonstrates the symmetric nature of SHM about the equilibrium position. Example: For F = -50x with v₀ = 10 m/s at center, amplitude A = √(2E/k) = √(50J/50N/m) = 1m.


  ### Mathematical Description of SHM

  Starting from F = -kx and Newton's second law, we derive the complete mathematical description. The acceleration a = -ω²x where ω = √(k/m). Using calculus: dv/dt = -ω²x leads to v dv/dx = -ω²x. Integrating with initial conditions (x₀, v₀) at t=0 gives v² = v₀² + ω²x₀² - ω²x². Defining A² = (v₀/ω)² + x₀², we get v = ω√(A² - x²). Further integration yields x = A sin(ωt + δ) where δ = sin⁻¹(x₀/A). The velocity is v = Aω cos(ωt + δ). These equations completely describe the position and velocity at any time t, showing the sinusoidal nature of SHM with amplitude A and angular frequency ω.


  ### Key Parameters of SHM

  SHM is characterized by several fundamental parameters: (1) Amplitude (A): Maximum displacement from equilibrium, determines the range of motion (-A to +A). (2) Time Period (T): Time for one complete oscillation, T = 2π/ω = 2π√(m/k). (3) Frequency (f): Number of oscillations per unit time, f = 1/T = ω/2π = (1/2π)√(k/m), measured in Hz. (4) Angular Frequency (ω): ω = 2πf = √(k/m), determines how rapidly the phase changes. (5) Phase (ωt + δ): Determines the instantaneous state of the oscillator. (6) Phase Constant (δ): Depends on initial conditions, can be chosen based on when t=0 is defined. Example: For m=200g, k=80N/m, T = 2π√(0.2/80) = 0.31s.


  ### SHM as Projection of Circular Motion

  A profound connection exists between SHM and uniform circular motion. Consider a particle moving in a circle of radius A with constant angular speed ω. The projections on perpendicular diameters give: x = A cos(ωt) and y = A sin(ωt). Each projection represents SHM with amplitude A and angular frequency ω, but with phases differing by π/2. This geometric interpretation provides intuitive understanding: (1) The amplitude A is the radius of the reference circle, (2) Angular frequency ω is the rate of rotation, (3) Phase differences correspond to different starting positions on the circle. This connection helps visualize SHM and explains why trigonometric functions naturally describe oscillatory motion. It also provides a method for analyzing complex oscillations by decomposing them into circular components.


  ### Energy in SHM

  Energy analysis reveals the conservative nature of ideal SHM. The potential energy U(x) = ½kx² = ½mω²x², derived from work done against the restoring force. Kinetic energy K = ½mv². For x = A sin(ωt + δ) and v = Aω cos(ωt + δ): U = ½mω²A² sin²(ωt + δ) and K = ½mω²A² cos²(ωt + δ). Total energy E = U + K = ½mω²A² (constant). Energy oscillates between kinetic and potential forms: (1) At equilibrium (x=0): all kinetic (K = ½mω²A²), (2) At extremes (x=±A): all potential (U = ½mω²A²). This constant total energy demonstrates conservation and determines amplitude from initial conditions. Example: For m=40g, A=2cm, T=0.2s, total energy E = 2π²mA²/T² = 7.9×10⁻³J.


  ### Angular SHM

  Angular simple harmonic motion occurs when a body oscillates rotationally about an equilibrium position. The defining equation is Γ = -kθ, where Γ is restoring torque and θ is angular displacement. For moment of inertia I, angular acceleration α = Γ/I = -(k/I)θ = -ω²θ, where ω = √(k/I). The solution is θ = θ₀ sin(ωt + δ) with angular velocity Ω = θ₀ω cos(ωt + δ). Time period T = 2π√(I/k) and frequency f = (1/2π)√(k/I). Energy: potential U = ½kθ² = ½Iω²θ², kinetic K = ½IΩ², total E = ½Iω²θ₀². Examples include torsional oscillations, compound pendulums, and rotating systems. The mathematics parallels linear SHM with angular quantities replacing linear ones.


  ### Simple Pendulum

  A simple pendulum consists of a point mass suspended by a massless, inextensible string of length l. For small angular displacements θ, the restoring torque Γ = -mgl sin θ ≈ -mglθ (for small θ, sin θ ≈ θ). With moment of inertia I = ml², the equation becomes d²θ/dt² = -(g/l)θ, giving ω = √(g/l). Time period T = 2π√(l/g), independent of mass and amplitude (for small oscillations). This provides a method to measure g: T = 2π√(l/g) gives g = 4π²l/T². The approximation sin θ ≈ θ is valid for θ < 15°. For larger amplitudes, the motion is not simple harmonic and the period increases. Example: For l=1m, g=π²m/s², T = 2π√(1/π²) = 2s. Laboratory measurement: 20 oscillations in 36s gives T=1.8s, so g = 4π²(0.8)/(1.8)² = 9.75 m/s².


  ### Physical Pendulum

  A physical pendulum is any rigid body suspended from a fixed point and oscillating under gravity. For a body with moment of inertia I about the suspension point, center of mass distance l from pivot, the restoring torque is Γ = -mgl sin θ ≈ -mglθ for small θ. The equation of motion: d²θ/dt² = -(mgl/I)θ = -ω²θ where ω = √(mgl/I). Time period T = 2π√(I/mgl). This reduces to simple pendulum when I = ml² (point mass). For a uniform rod of length L suspended from one end: I = mL²/3, l = L/2, so T = 2π√(2L/3g). Example: For L=1m rod, T = 2π√(2×1/3×9.8) = 1.64s. The physical pendulum demonstrates how mass distribution affects oscillation period.


  ### Torsional Pendulum

  A torsional pendulum consists of a body suspended by a wire that provides a restoring torque proportional to twist angle. When rotated through angle θ, the wire exerts torque Γ = -kθ where k is the torsional constant of the wire. For moment of inertia I, the equation becomes d²θ/dt² = -(k/I)θ = -ω²θ where ω = √(k/I). Time period T = 2π√(I/k). This system demonstrates pure rotational SHM without gravitational effects. The torsional constant k depends on wire material, length, and cross-section. Energy: U = ½kθ², K = ½IΩ², total E = ½kθ₀². Example: For a disc with I = mr²/2 = 2.5×10⁻⁴ kg⋅m², T = 0.2s, the torsional constant k = 4π²I/T² = 0.25 kg⋅m²/s².


  ### Composition of SHM

  When multiple SHM forces act on a particle, the resultant motion is the vector sum of individual motions. For two SHM in the same direction: x₁ = A₁ sin ωt and x₂ = A₂ sin(ωt + δ), the resultant is x = A sin(ωt + ε) where A = √(A₁² + A₂² + 2A₁A₂ cos δ) and tan ε = A₂ sin δ/(A₁ + A₂ cos δ). Special cases: (1) δ = 0 (in phase): A = A₁ + A₂, (2) δ = π (out of phase): A = |A₁ - A₂|. Vector method: represent each SHM as a vector with magnitude equal to amplitude, add vectorially. For perpendicular SHM: x = A₁ sin ωt, y = A₂ sin(ωt + δ), the path is generally elliptical: x²/A₁² + y²/A₂² - (2xy cos δ)/(A₁A₂) = sin² δ. Special cases: δ = 0 gives straight line, δ = π/2 gives ellipse, δ = π/2 with A₁ = A₂ gives circle.


  ### Damped and Forced Oscillations

  Real oscillators experience damping forces that oppose motion, typically F_damping = -bv. The equation becomes m(dv/dt) = -kx - bv. For small damping, the solution is x = A₀e^(-bt/2m) sin(ω't + δ) where ω' = √(ω₀² - (b/2m)²) and ω₀ = √(k/m). The amplitude decreases exponentially while frequency slightly decreases. Critical damping occurs when oscillation just ceases. For forced oscillations, an external periodic force F₀ sin Ωt is applied. After transients die out, steady-state motion is x = A sin(Ωt - φ) where A = F₀/m/√[(ω₀² - Ω²)² + (bΩ/m)²]. Resonance occurs when Ω ≈ ω₀, giving maximum amplitude. At resonance, energy input compensates for damping losses. Small damping gives sharp resonance with large amplitude. This phenomenon is crucial in engineering design to avoid destructive resonances (like the Tacoma Narrows Bridge collapse in 1940).


## Relationships

- **Definition and Basic Concepts** --[leads_to]--> **Qualitative Nature of SHM** (Basic definition leads to understanding physical behavior of oscillating systems)
- **Definition and Basic Concepts** --[prerequisite]--> **Mathematical Description of SHM** (Force equation F = -kx is needed to derive the complete mathematical solution)
- **Mathematical Description of SHM** --[leads_to]--> **Key Parameters of SHM** (Mathematical solution reveals fundamental parameters like amplitude, period, and frequency)
- **Mathematical Description of SHM** --[related]--> **SHM as Projection of Circular Motion** (Trigonometric solutions connect SHM to circular motion geometry)
- **Key Parameters of SHM** --[prerequisite]--> **Energy in SHM** (Understanding amplitude and frequency is needed to analyze energy transformations)
- **Definition and Basic Concepts** --[leads_to]--> **Angular SHM** (Linear SHM concepts extend to rotational oscillations with analogous equations)
- **Angular SHM** --[example_of]--> **Simple Pendulum** (Simple pendulum is a specific application of angular SHM principles)
- **Angular SHM** --[example_of]--> **Physical Pendulum** (Physical pendulum demonstrates angular SHM for extended rigid bodies)
- **Angular SHM** --[example_of]--> **Torsional Pendulum** (Torsional pendulum shows pure angular SHM without gravitational restoring force)
- **Mathematical Description of SHM** --[prerequisite]--> **Composition of SHM** (Understanding individual SHM solutions is needed to analyze combined motions)
- **Energy in SHM** --[prerequisite]--> **Damped and Forced Oscillations** (Energy conservation in ideal SHM provides foundation for understanding energy loss in damped systems)
- **Key Parameters of SHM** --[prerequisite]--> **Damped and Forced Oscillations** (Natural frequency and resonance concepts require understanding of basic SHM parameters)
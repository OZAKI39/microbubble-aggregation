// Settled harmonic response of APECSS bubbles, measured cycle by cycle (one source, two builds).
//
// The bubble equations, shell law, gas law and RK54 integrator are APECSS's own and are not
// modified. This file only
//   1. replaces APECSS's real sine drive by a complex drive p_inf(t) = p0 + Re[P exp(i w t)];
//   2. adds running Fourier tallies as APECSS user ODEs, so every acoustic cycle directly yields
//      the volume harmonics n = 0..8 (stored times 2^-200 so they never limit the time step);
//   3. advances whole cycles until the harmonics no longer change (estimated remaining relative
//      error below tol) and flags period doubling, non-convergence and solver failure.
// Tallies of one cycle: mean = <(V - V0)/V0>, c_n = 2<(V - V0)/V0 cos(n w t)>,
// s_n = 2<(V - V0)/V0 sin(n w t)>, so W_n = V0 (c_n - i s_n) is the n-th volume harmonic
// relative to exp(i n w t): V(t) - V0 = V0 mean + Re sum_n W_n exp(i n w t).
//
// Command line (default build): one bubble started from rest; the settled response used to build
// and check response tables. Drive p0 - P sin(w t) = p0 + Re[P exp(i theta)], theta = w t + pi/2
// (APECSS's sine convention, as in the frozen tables), i.e. complex amplitude i P; the reported
// V_n = W_n (-i)^n is relative to exp(i n theta).
//   usage: apecss_harmonics -options FILE -freq F -amp P [-tol 1e-6] [-mincycles 4]
//                           [-maxcycles 400] [-cycles N] [-history]
//   -cycles N runs exactly N cycles (no early stop) and reports cycle N.
//   The result is one line on stdout starting with "APECSS_HARMONICS_JSON ".
//
// Shared library (-DAPECSS_HARMONICS_LIBRARY): carried bubbles for the pretraining tier. Every
// bubble keeps its own APECSS radial state (radius and wall velocity) between simulation steps.
// At each step it continues from that state under its new local complex drive P and advances
// whole cycles until settled (usually one); W_n then has the convention of the response tables
// (V_n(P) = V_n(|P|) exp(i n arg P)). Bubbles are independent and run in parallel (OpenMP).

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "apecss.h"

#define NH 8  // harmonics 1..8, as in the response tables
#define NT (2 * NH + 1)  // tallies: mean, then cos/sin for each harmonic
#define TALLY_EXP 200  // tallies are stored times 2^-200 so they never limit the APECSS time step
#define Q_MAX 0.99  // largest cycle-to-cycle contraction q the settling estimate admits
// Smallest fundamental |W_1|/V0 that changes are measured against (2026-11-08). Near a pressure
// node the drive and the response shrink together until the tallies are round-off (absolute
// noise about 1e-15 to 2e-14 below 1e-6 Pa); relative to the bubble's own fundamental the change
// then never settles. 1e-6 is the response to about 0.2 Pa at 2.5 MHz and 4 Pa at 10 MHz, far
// below the responses that make the forces (1e-3 to 1e-1 at 0.1 to 10 kPa) and far above the
// round-off.
#define FUND_FLOOR 1.0e-6

enum
{
  CARRIED_CONVERGED = 0,
  CARRIED_NOT_CONVERGED = 1,
  CARRIED_PERIOD_DOUBLING = 2,
  CARRIED_SOLVER_FAILED = 3,
  CARRIED_ZERO_DRIVE = 4,
  CARRIED_FIXED_CYCLES = 5
};

struct CarriedBubble
{
  struct APECSS_Bubble *B;
  struct APECSS_Gas *Gas;
  struct APECSS_Liquid *Liquid;
  struct APECSS_Interface *Interface;
  struct APECSS_NumericsODE *Numerics;
  struct APECSS_Excitation *Excitation;
  int first;  // index of the first tally ODE
  double omega, T, R0;
  double p_re, p_im;  // complex drive amplitude [Pa]
  double cache_t, cache_R, cache_w, cache_c[NH + 1], cache_s[NH + 1];
  int cache_valid;
  double H[NT], Hprev[NT];  // tallies of the last two cycles
  int cycles_seen;  // cycles with valid tallies since creation
  double q;  // last measured contraction of the cycle-to-cycle change
  int q_known;  // q has been measured (two ratios in the first call)
  int calls_since_q;  // calls since q was last measured (q ages while the bubble moves)
  double Rmax, Rmin;  // radius extrema of the current cycle
  long cycles_total, steps_total;
};

// Settling rule of one call.
struct Settle
{
  double tol;  // stop when the estimated remaining relative error <= tol
  int min_cycles;  // at least this many cycles in this call
  int max_cycles;  // NOT_CONVERGED after this many cycles in this call
  int q_refresh;  // at least two cycles every q_refresh calls, so q is re-measured
  int fixed;  // 1: run exactly max_cycles without early stop (FIXED_CYCLES)
};

// Optional per-cycle record, index 1..cycles: fundamental |W_1|/V0, changes and estimate.
struct CycleLog
{
  double *fund, *d1, *d2, *est;
};

static _Thread_local struct CarriedBubble *CURRENT;  // bubble being advanced (progress hook)

static void tally_cache(struct CarriedBubble *b, APECSS_FLOAT *Sol, APECSS_FLOAT t)
{
  if (b->cache_valid && t == b->cache_t && Sol[1] == b->cache_R) return;
  double x = (Sol[1] - b->R0) / b->R0;
  // (R/R0)^3 - 1 without cancellation, scaled by 2^-TALLY_EXP (exact)
  b->cache_w = ldexp(x * (3.0 + x * (3.0 + x)), -TALLY_EXP);
  double th = b->omega * t, c1 = cos(th), s1 = sin(th);
  b->cache_c[0] = 1.0;
  b->cache_s[0] = 0.0;
  for (int n = 1; n <= NH; n++)
  {
    b->cache_c[n] = b->cache_c[n - 1] * c1 - b->cache_s[n - 1] * s1;
    b->cache_s[n] = b->cache_s[n - 1] * c1 + b->cache_c[n - 1] * s1;
  }
  b->cache_t = t;
  b->cache_R = Sol[1];
  b->cache_valid = 1;
}

#define TALLY(name, arr, n)                                                             \
  static APECSS_FLOAT name(APECSS_FLOAT *Sol, APECSS_FLOAT t, struct APECSS_Bubble *B) \
  {                                                                                     \
    struct CarriedBubble *b = (struct CarriedBubble *) B->user_data;                    \
    tally_cache(b, Sol, t);                                                             \
    return (b->cache_w * b->arr[n]);                                                    \
  }
TALLY(tally_c0, cache_c, 0)
TALLY(tally_c1, cache_c, 1)
TALLY(tally_s1, cache_s, 1)
TALLY(tally_c2, cache_c, 2)
TALLY(tally_s2, cache_s, 2)
TALLY(tally_c3, cache_c, 3)
TALLY(tally_s3, cache_s, 3)
TALLY(tally_c4, cache_c, 4)
TALLY(tally_s4, cache_s, 4)
TALLY(tally_c5, cache_c, 5)
TALLY(tally_s5, cache_s, 5)
TALLY(tally_c6, cache_c, 6)
TALLY(tally_s6, cache_s, 6)
TALLY(tally_c7, cache_c, 7)
TALLY(tally_s7, cache_s, 7)
TALLY(tally_c8, cache_c, 8)
TALLY(tally_s8, cache_s, 8)
static APECSS_FLOAT (*const TALLIES[NT])(APECSS_FLOAT *, APECSS_FLOAT, struct APECSS_Bubble *) = {
    tally_c0, tally_c1, tally_s1, tally_c2, tally_s2, tally_c3, tally_s3, tally_c4, tally_s4,
    tally_c5, tally_s5, tally_c6, tally_s6, tally_c7, tally_s7, tally_c8, tally_s8};

static APECSS_FLOAT pressure_infinity(APECSS_FLOAT t, struct APECSS_Bubble *B)
{
  struct CarriedBubble *b = (struct CarriedBubble *) B->user_data;
  double th = b->omega * t;
  return (B->p0 + b->p_re * cos(th) - b->p_im * sin(th));
}

static APECSS_FLOAT pressurederivative_infinity(APECSS_FLOAT t, struct APECSS_Bubble *B)
{
  struct CarriedBubble *b = (struct CarriedBubble *) B->user_data;
  double th = b->omega * t;
  return (-b->omega * (b->p_re * sin(th) + b->p_im * cos(th)));
}

// Called by APECSS after every accepted time step (progress hook): radius extrema of the cycle.
static int track_extrema(int *prog, APECSS_FLOAT t, APECSS_FLOAT totaltime)
{
  struct CarriedBubble *b = CURRENT;
  struct APECSS_Bubble *B = b->B;
  double R = B->ODEsSol[1], U = B->ODEsSol[0], Rold = B->ODEsSolOld[1], Uold = B->ODEsSolOld[0];
  if (R > b->Rmax) b->Rmax = R;
  if (R < b->Rmin) b->Rmin = R;
  if (Uold * U < 0.0 && B->dt > 0.0)
  {
    // Turning point inside the step: constant-acceleration estimate of the extremum.
    double a = (U - Uold) / B->dt, Rx = Rold - 0.5 * Uold * Uold / a;
    if (Rx > b->Rmax) b->Rmax = Rx;
    if (Rx < b->Rmin) b->Rmin = Rx;
  }
  return (0);
}

static int progress_none() { return (0); }

// One bubble at rest, read from an APECSS options file; the drive is set per call.
void *carried_create(const char *options, double frequency_Hz)
{
  struct CarriedBubble *b = calloc(1, sizeof(struct CarriedBubble));
  char path[APECSS_STRINGLENGTH];
  snprintf(path, APECSS_STRINGLENGTH, "%s", options);
  b->B = malloc(sizeof(struct APECSS_Bubble));
  apecss_bubble_initializestruct(b->B);
  apecss_bubble_setdefaultoptions(b->B);
  apecss_bubble_readoptions(b->B, path);
  b->Gas = malloc(sizeof(struct APECSS_Gas));
  b->Liquid = malloc(sizeof(struct APECSS_Liquid));
  b->Interface = malloc(sizeof(struct APECSS_Interface));
  b->Numerics = malloc(sizeof(struct APECSS_NumericsODE));
  apecss_gas_setdefaultoptions(b->Gas);
  apecss_liquid_setdefaultoptions(b->Liquid);
  apecss_interface_setdefaultoptions(b->Interface);
  apecss_odesolver_setdefaultoptions(b->Numerics);
  apecss_gas_readoptions(b->Gas, path);
  apecss_liquid_readoptions(b->Liquid, path);
  apecss_interface_readoptions(b->Interface, path);
  apecss_odesolver_readoptions(b->Numerics, path);
  b->B->Gas = b->Gas;
  b->B->Liquid = b->Liquid;
  b->B->Interface = b->Interface;
  b->B->NumericsODE = b->Numerics;
  b->T = 1.0 / frequency_Hz;
  b->omega = 2.0 * APECSS_PI * frequency_Hz;
  b->B->tStart = 0.0;
  b->B->tEnd = 1.0e6 * b->T;  // only passed to the progress hook
  b->B->dt = APECSS_MIN(1.0e-7, b->T / 64.0);  // initial time step, adapted by APECSS
  b->Excitation = malloc(sizeof(struct APECSS_Excitation));
  b->Excitation->type = APECSS_EXCITATION_SIN;  // selects the excitation path; replaced below
  b->Excitation->f = frequency_Hz;
  b->Excitation->dp = 0.0;
  b->B->Excitation = b->Excitation;
  b->B->nUserODEs = NT;
  b->B->nODEs += NT;
  apecss_gas_processoptions(b->Gas);
  apecss_liquid_processoptions(b->Liquid);
  apecss_interface_processoptions(b->Interface);
  apecss_odesolver_processoptions(b->Numerics);
  apecss_bubble_processoptions(b->B);
  b->B->get_pressure_infinity = pressure_infinity;
  b->B->get_pressurederivative_infinity = pressurederivative_infinity;
  b->B->progress_initial = progress_none;
  b->B->progress_update = track_extrema;
  b->B->progress_final = progress_none;
  b->B->user_data = b;
  apecss_bubble_initialize(b->B);
  b->first = b->B->nODEs;
  for (int j = 0; j < NT; j++)
  {
    b->B->ode[b->first + j] = TALLIES[j];
    b->B->ODEsSol[b->first + j] = 0.0;
  }
  b->B->nODEs += NT;
  b->R0 = b->B->R0;
  b->q = 0.9;  // conservative until a contraction is measured
  return (b);
}

double carried_rest_volume(void *h)
{
  struct CarriedBubble *b = h;
  return (4.0 / 3.0 * APECSS_PI * pow(b->R0, 3));
}

// Continue a carried bubble at another drive frequency (a switch between pretraining segments).
// Its radial, wall and gas state carry over unchanged, so the bubble itself is continuous.
// Every call starts at drive phase 0 (t = 0, the drive is periodic) and ends after whole
// cycles, so the drive phase is continuous as well; only the drive frequency and amplitude
// change. The settling decay rate q was measured at the old frequency: it is measured again,
// as in a first call (at least three cycles in the next call). Returns 0, or 1 for an invalid
// frequency (nothing changed).
int carried_set_frequency(void *h, double frequency_Hz)
{
  struct CarriedBubble *b = h;
  if (!isfinite(frequency_Hz) || !(frequency_Hz > 0.0)) return (1);
  b->T = 1.0 / frequency_Hz;
  b->omega = 2.0 * APECSS_PI * frequency_Hz;
  b->Excitation->f = frequency_Hz;
  b->B->tEnd = 1.0e6 * b->T;  // only passed to the progress hook
  b->B->dt = APECSS_MIN(b->B->dt, b->T / 64.0);  // first step at most 1/64 cycle, then adapted
  b->q = 0.9;  // conservative until a contraction is measured again
  b->q_known = 0;
  b->calls_since_q = 0;
  b->cache_valid = 0;
  return (0);
}

static double max_change(const double *a, const double *c, double ref)
{
  // largest change of any tally (mean, cos, sin parts) relative to ref (the fundamental magnitude, at least FUND_FLOOR)
  double m = 0.0;
  for (int j = 0; j < NT; j++)
    if (fabs(a[j] - c[j]) > m) m = fabs(a[j] - c[j]);
  return (m / ref);
}

// Advance one bubble at drive (p_re, p_im) from its current state; H_out gets the last cycle's
// tallies, Rext its radius extrema over R0 (min, max). Returns a CARRIED_* status.
static int advance(struct CarriedBubble *b, double p_re, double p_im, struct Settle s, struct CycleLog *log, double *H_out, int *cycles,
                   double *est_out, double *Rext)
{
  // A single cycle cannot measure the decay rate q, so with one cycle per step the stop
  // estimate would keep using an old q. Near the shell transition q grows (slower settling)
  // and an old q is optimistic; every q_refresh calls at least two cycles re-measure it.
  if (b->calls_since_q >= s.q_refresh && s.min_cycles < 2) s.min_cycles = 2;
  int measured = 0;
  *cycles = 0;
  *est_out = INFINITY;
  if (p_re == 0.0 && p_im == 0.0)
  {
    for (int j = 0; j < NT; j++) H_out[j] = 0.0;
    return (CARRIED_ZERO_DRIVE);
  }
  struct APECSS_Bubble *B = b->B;
  CURRENT = b;
  b->p_re = p_re;
  b->p_im = p_im;
  b->steps_total += B->dtNumber;
  apecss_bubble_solver_initialize(B);  // t = 0 (the drive is periodic) and FSAL slope for the new drive
  double floor = 1.0e-3 * s.tol, d_prev = INFINITY, ratio_prev = -1.0;
  // A change d1 <= settled bounds the remaining error by tol for any q <= Q_MAX
  // (d1 q / (1 - q) <= tol), without a measured q (2026-11-08). With the ODE tolerance 1e-8 the
  // change at 3-10 MHz levels off at 1e-6 to 1e-5 of the fundamental (integration noise): the
  // ratios are then noise, q reads >= 0.9 (no estimate), and the bubble ran to max_cycles waiting
  // for the round-off floor.
  double settled = s.tol * (1.0 - Q_MAX) / Q_MAX;
  int status = s.fixed ? CARRIED_FIXED_CYCLES : CARRIED_NOT_CONVERGED, p2 = 0;
  for (int k = 1; k <= s.max_cycles; k++)
  {
    for (int j = 0; j < NT; j++) B->ODEsSol[b->first + j] = 0.0;
    b->cache_valid = 0;
    b->Rmax = b->Rmin = B->ODEsSol[1];
    apecss_bubble_solver_run(k * b->T, B);
    *cycles = k;
    b->cycles_total++;
    if (!isfinite(B->ODEsSol[1]) || !(B->ODEsSol[1] > 0.0) || !isfinite(B->ODEsSol[0])) return (CARRIED_SOLVER_FAILED);
    double Hk[NT];
    for (int j = 0; j < NT; j++)
    {
      double v = ldexp(B->ODEsSol[b->first + j], TALLY_EXP) / b->T;
      Hk[j] = j == 0 ? v : 2.0 * v;
    }
    double fund = hypot(Hk[1], Hk[2]);
    if (!isfinite(fund)) return (CARRIED_SOLVER_FAILED);
    double ref = fmax(fund, FUND_FLOOR);
    double d1 = b->cycles_seen >= 1 ? max_change(Hk, b->H, ref) : INFINITY;
    double d2 = b->cycles_seen >= 2 ? max_change(Hk, b->Hprev, ref) : INFINITY;
    memcpy(b->Hprev, b->H, sizeof(b->H));
    memcpy(b->H, Hk, sizeof(Hk));
    b->cycles_seen++;
    Rext[0] = b->Rmin / b->R0;
    Rext[1] = b->Rmax / b->R0;
    // Contraction of the change from one cycle to the next. The free ringing near f0 is
    // sampled once per drive cycle, so single ratios fluctuate: the larger of the last two
    // ratios is used. Before any q is known (first call) two ratios are required.
    if (isfinite(d_prev) && d_prev > floor && isfinite(d1) && d1 > floor)
    {
      double ratio = d1 / d_prev;
      if (ratio_prev > 0.0 || b->q_known)
      {
        b->q = fmin(ratio_prev > 0.0 ? fmax(ratio, ratio_prev) : ratio, Q_MAX);
        b->q_known = 1;
        measured = 1;
      }
      ratio_prev = ratio;
    }
    double q = b->q, est = q < 0.9 ? d1 * q / (1.0 - q) : INFINITY;
    if (d1 <= floor) est = d1;  // round-off level: the ratio is meaningless
    if (d1 <= settled) est = fmin(est, s.tol);  // at most tol for any q <= Q_MAX
    *est_out = est;
    d_prev = d1;
    if (log)
    {
      log->fund[k] = fund;
      log->d1[k] = d1;
      log->d2[k] = d2;
      log->est[k] = est;
    }
    if (s.fixed) continue;
    if (k >= s.min_cycles && est <= s.tol)
    {
      status = CARRIED_CONVERGED;
      break;
    }
    // Period doubling: cycle k equals cycle k-2 but not k-1, twice in a row.
    if (k >= s.min_cycles + 2 && d2 <= s.tol && d1 > 1.0e3 * fmax(d2, floor) && d1 > 10.0 * s.tol)
    {
      if (++p2 >= 2)
      {
        status = CARRIED_PERIOD_DOUBLING;
        break;
      }
    }
    else
      p2 = 0;
  }
  b->calls_since_q = measured ? 0 : b->calls_since_q + 1;
  memcpy(H_out, b->H, sizeof(b->H));
  return (status);
}

// All bubbles of one force evaluation; bubbles are independent, so they run in parallel.
// A bubble that has never been advanced starts from rest and needs min_cycles_cold cycles.
// Returns the number of bubbles that did not converge (statuses in status[]).
int carried_advance(void **bubbles, int n, const double *p_re, const double *p_im, double tol, int min_cycles_warm, int min_cycles_cold,
                    int max_cycles, int q_refresh, int threads, double *H_out, int *cycles, int *status, double *est, double *Rext)
{
  int failures = 0;
#ifdef _OPENMP
#pragma omp parallel for num_threads(threads) schedule(dynamic, 1) reduction(+ : failures)
#endif
  for (int i = 0; i < n; i++)
  {
    struct CarriedBubble *b = bubbles[i];
    struct Settle s = {tol, b->cycles_seen == 0 ? min_cycles_cold : min_cycles_warm, max_cycles, q_refresh, 0};
    status[i] = advance(b, p_re[i], p_im[i], s, NULL, H_out + (size_t) i * NT, cycles + i, est + i, Rext + 2 * i);
    if (status[i] != CARRIED_CONVERGED && status[i] != CARRIED_ZERO_DRIVE) failures++;
  }
  return (failures);
}

void carried_stats(void *h, long *cycles_total, long *steps_total)
{
  struct CarriedBubble *b = h;
  *cycles_total = b->cycles_total;
  *steps_total = b->steps_total + b->B->dtNumber;
}

void carried_free(void *h)
{
  struct CarriedBubble *b = h;
  apecss_bubble_freestruct(b->B);
  free(b->B);
  free(b->Gas);
  free(b->Liquid);
  free(b->Interface);
  free(b->Numerics);
  free(b->Excitation);
  free(b);
}

#ifndef APECSS_HARMONICS_LIBRARY

static double finite_or(double v, double fallback) { return (isfinite(v) ? v : fallback); }

int main(int argc, char **args)
{
  char options[APECSS_STRINGLENGTH];
  double fa = 0.0, pa = 0.0, tol = 1.0e-6;
  int mincycles = 4, maxcycles = 400, fixedcycles = 0, history = 0;
  options[0] = '\0';

  int i = 1;
  while (i < argc)
  {
    if (strcmp("-options", args[i]) == 0 && i + 1 < argc)
      snprintf(options, APECSS_STRINGLENGTH, "%s", args[++i]);
    else if (strcmp("-freq", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%le", &fa);
    else if (strcmp("-amp", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%le", &pa);
    else if (strcmp("-tol", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%le", &tol);
    else if (strcmp("-mincycles", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%d", &mincycles);
    else if (strcmp("-maxcycles", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%d", &maxcycles);
    else if (strcmp("-cycles", args[i]) == 0 && i + 1 < argc)
      sscanf(args[++i], "%d", &fixedcycles);
    else if (strcmp("-history", args[i]) == 0)
      history = 1;
    else
    {
      fprintf(stderr, "apecss_harmonics: unknown or incomplete option %s\n", args[i]);
      return (2);
    }
    i++;
  }
  if (options[0] == '\0' || !(fa > 0.0) || !(pa > 0.0) || !(tol > 0.0) || mincycles < 3 || maxcycles < mincycles || fixedcycles < 0)
  {
    fprintf(stderr, "apecss_harmonics: need -options, -freq > 0, -amp > 0, -tol > 0, 3 <= mincycles <= maxcycles\n");
    return (2);
  }
  int ncycles = fixedcycles > 0 ? fixedcycles : maxcycles;

  struct CarriedBubble *b = carried_create(options, fa);
  b->B->tEnd = ncycles * b->T;
  struct CycleLog log = {calloc(ncycles + 1, sizeof(double)), calloc(ncycles + 1, sizeof(double)), calloc(ncycles + 1, sizeof(double)),
                         calloc(ncycles + 1, sizeof(double))};
  struct Settle s = {tol, mincycles, ncycles, 1 << 30, fixedcycles > 0};
  double H[NT], est = INFINITY, Rext[2] = {0.0, 0.0};
  int k = 0;

  clock_t start = clock();
  int code = advance(b, 0.0, pa, s, &log, H, &k, &est, Rext);  // complex amplitude i P: p0 - P sin(w t)
  double cpu = (double) (clock() - start) / CLOCKS_PER_SEC;
  const char *names[] = {"CONVERGED", "NOT_CONVERGED", "PERIOD_DOUBLING", "SOLVER_FAILED", "ZERO_DRIVE", "FIXED_CYCLES"};
  const char *status = names[code];
  double V0 = carried_rest_volume(b);

  if (code == CARRIED_SOLVER_FAILED)  // no valid cycle values to report
  {
    printf("APECSS_HARMONICS_JSON {\"status\": \"%s\", \"cycles\": %d, \"frequency_Hz\": %.17g, \"pressure_Pa\": %.17g, \"cpu_s\": %.6g}\n", status, k,
           fa, pa, cpu);
    return (3);
  }
  // V_n = W_n (-i)^n with W_n = V0 (c_n - i s_n): rotation by a multiple of 90 degrees (exact)
  double re[NH + 1], im[NH + 1];
  for (int n = 1; n <= NH; n++)
  {
    double a = H[2 * n - 1] * V0, c = -H[2 * n] * V0;
    re[n] = n % 4 == 0 ? a : n % 4 == 1 ? c : n % 4 == 2 ? -a : -c;
    im[n] = n % 4 == 0 ? c : n % 4 == 1 ? -a : n % 4 == 2 ? -c : a;
  }
  printf("APECSS_HARMONICS_JSON {\"status\": \"%s\", \"cycles\": %d, \"frequency_Hz\": %.17g, \"pressure_Pa\": %.17g, ", status, k, fa, pa);
  printf("\"radius_m\": %.17g, \"rest_volume_m3\": %.17g, \"tolerance\": %.17g, \"min_cycles\": %d, \"max_cycles\": %d, ", b->R0, V0, tol, mincycles,
         ncycles);
  printf("\"ode_tolerance\": %.17g, \"rp_model\": %d, \"lipid_model\": %d, ", (double) b->Numerics->tol, b->B->RPModel,
         b->Interface->LipidCoatingModel);
  printf("\"estimated_relative_error\": %.17g, \"last_relative_change\": %.17g, \"lag2_relative_change\": %.17g, ", finite_or(est, -1.0),
         finite_or(log.d1[k], -1.0), finite_or(log.d2[k], -1.0));
  printf("\"mean_volume_change_m3\": %.17g, \"harmonics_re_m3\": [", H[0] * V0);
  for (int n = 1; n <= NH; n++) printf("%.17g%s", re[n], n < NH ? ", " : "], \"harmonics_im_m3\": [");
  for (int n = 1; n <= NH; n++) printf("%.17g%s", im[n], n < NH ? ", " : "], ");
  printf("\"max_R_over_R0\": %.17g, \"min_R_over_R0\": %.17g, \"time_steps\": %d, \"sub_iterations\": %d, \"cpu_s\": %.6g", Rext[1], Rext[0],
         b->B->dtNumber, b->B->nSubIter, cpu);
  if (history)
  {
    printf(", \"history\": [");
    for (int j = 1; j <= k; j++)
      printf("[%d, %.17g, %.17g, %.17g, %.17g]%s", j, log.fund[j] * V0, finite_or(log.d1[j], -1.0), finite_or(log.d2[j], -1.0),
             finite_or(log.est[j], -1.0), j < k ? ", " : "");
    printf("]");
  }
  printf("}\n");

  apecss_bubble_solver_finalize(b->B);
  carried_free(b);
  free(log.fund);
  free(log.d1);
  free(log.d2);
  free(log.est);
  return (0);
}

#endif

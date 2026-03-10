/* ------------------------------------------------------------
 * PSEUDOCODE: Non-stop extension for the Chains model
 * Style A: bounded step window over a cyclic "always-on" workload
 * ------------------------------------------------------------ */

#define MAX_STEPS 20

byte steps = 0;
bit done = 0;

/* Allocation tracking to prevent reusing addresses already in the chain */
bool used[MEM_SIZE];

/* Reset model state so a run starts from a known configuration */
inline reset_chain_state() {
  int i;

  chain.head = 0;
  chain.tail = 0;
  chain.size = 0;
  nptr = 0;

  i = 0;
  do
  :: (i == MEM_SIZE) -> break
  :: else ->
      used[i] = false;

      /* Optional: clear memory to avoid unintended carry-over */
      memory[i].nxt = 0;
      memory[i].prv = 0;
      memory[i].itm = 0;

      i++
  od
}

/* Trace window controller: ensures finite verification/test generation */
proctype TraceWindow() {
  do
  :: (steps < MAX_STEPS) -> steps++
  :: else -> done = 1; break
  od
}

/* Choose an address from the bounded valid pool 1..7 (0 is NULL) */
inline choose_addr(addr) {
  if
  :: addr = 1
  :: addr = 2
  :: addr = 3
  :: addr = 4
  :: addr = 5
  :: addr = 6
  :: addr = 7
  fi
}

/* Choose a stored value from a bounded range (initially 0..7) */
inline choose_val(val) {
  if
  :: val = 0
  :: val = 1
  :: val = 2
  :: val = 3
  :: val = 4
  :: val = 5
  :: val = 6
  :: val = 7
  fi
}

/* Always-on environment: repeatedly selects append or get while not done */
proctype NonStopEnv() {
  int addr;
  int val;

  do
  :: done -> break

  /* Append case: only when chain not full and chosen addr is free */
  :: (chain.size < 7) ->
      choose_addr(addr);
      if
      :: (used[addr] == false) ->
          choose_val(val);
          used[addr] = true;
          run doAppend(addr, val);   /* uses existing atomic wrapper + logging */
      :: else -> skip
      fi

  /* Get case: only when chain non-empty */
  :: (chain.head != 0) ->
      run doNonNullGet();            /* blocks until non-empty, then performs get */
      used[nptr] = false;            /* free returned address for reuse */
  od
}

init {
  atomic {
    /* existing declarations/logging (as in original Chains model) */
    print_decls_and_init_metadata();

    reset_chain_state();
    show_chain();
    show_node();
  }

  run TraceWindow();
  run NonStopEnv();

  /* Wait for bounded window completion */
  do
  :: done -> break
  :: else -> skip
  od

#ifdef TEST_GEN
  assert(false);      /* force trail generation for test synthesis */
#else
  /* Example sanity check at end of bounded run (optional) */
  assert(chain.size <= 7);
#endif

  printf("@@@ Chains NonStop finished!\n");
}

/* ------------------------------------------------------------
 * PSEUDOCODE: Non-stop extension for the FreeChain model
 * Style A: bounded step window over a cyclic "always-on" workload
 *
 * Requirements:
 *  - keep append/get semantics unchanged
 *  - represent ongoing operation via repeated operations
 *  - bounded by MAX_STEPS so verification/test generation terminates
 *  - guarded choice to avoid generating lots of invalid trails
 *  - include TEST_GEN mode (assert(false)) like other models
 * ------------------------------------------------------------ */

#define MAX_STEPS 20

byte steps = 0;
bit done = 0;

/* Helper: reset model state so a run starts clean */
inline reset_freechain_state() {
  int i;

  chain.head = 0;
  chain.tail = 0;
  chain.size = 0;
  nptr = 0;

  /* clear memory to a known "free" state */
  i = 0;
  do
  :: (i == MEM_SIZE) -> break
  :: else ->
      memory[i].nxt = 0;
      memory[i].prv = 0;
      memory[i].itm = 0;
      memory0[i] = 0;
      i++
  od
}

/* Trace window controller */
proctype TraceWindow() {
  do
  :: (steps < MAX_STEPS) -> steps++
  :: else -> done = 1; break
  od
}

/* A node is "free" if:
 *  - addr != 0  (0 is NULL)
 *  - not currently head/tail (already enforced by append asserts)
 *  - its nxt == 0 (model’s notion of not currently linked)
 */
inline is_free_node(addr, ok) {
  ok = (addr != 0) &&
       (memory[addr].nxt == 0) &&
       (addr != chain.head) &&
       (addr != chain.tail) &&
       (chain.size < MEM_SIZE);
}

/* Guarded address chooser:
 * non-deterministically picks an address 1..7,
 * but only allows progress if it is currently free.
 */
inline choose_free_addr(addr) {
  do
  :: addr = 1; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 2; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 3; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 4; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 5; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 6; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  :: addr = 7; (memory[addr].nxt == 0 && addr != chain.head && addr != chain.tail) -> break
  od
}

/* Bounded payload values (initially 0..7 like Chains).
 * This can be widened later if manageable.
 */
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

/* Always-on environment workload */
proctype NonStopEnv() {
  int addr;
  int val;

  do
  :: done -> break

  /* Append branch:
   * only enabled when chain not full AND there exists some free node.
   * We express “exists a free node” by allowing choose_free_addr to succeed.
   */
  :: (chain.size < MEM_SIZE) ->
      choose_free_addr(addr);
      choose_val(val);
      run doAppend(addr, val);

  /* Get branch:
   * only enabled when chain non-empty.
   * Use doNonNullGet (blocks until non-empty, then performs get).
   */
  :: (chain.head != 0) ->
      run doNonNullGet()
  od
}

init {
  pid nr;

  atomic {
    /* Keep existing init logging format */
    printf("@@@ 0 NAME FreeChain_NonStop\n");
    printf("@@@ 0 DEF MAX_SIZE 8\n");
    printf("@@@ 0 DCLARRAY Node memory MAX_SIZE\n");
    printf("@@@ 0 DECL unsigned nptr NULL\n");
    printf("@@@ 0 DECL Control chain\n");

    printf("@@@ 0 INIT\n");
    reset_freechain_state();
    show_chain();
    show_node();
  }

  nr = _nr_pr;

  /* Preserve original “empty get” coverage once */
  run doGet();
  nr == _nr_pr;

  /* Start bounded non-stop workload */
  run TraceWindow();
  run NonStopEnv();

  /* Wait for bounded completion */
  do
  :: done -> break
  :: else -> skip
  od

#ifdef TEST_GEN
  assert(false);  /* generate trails for test synthesis */
#else
  /* Example consistency property: empty iff head==0 and tail==0 */
  assert( (chain.size == 0) == (chain.head == 0 && chain.tail == 0) );
#endif

  printf("@@@ 0 LOG FreeChain NonStop finished\n");
}

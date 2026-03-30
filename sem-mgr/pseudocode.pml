#define MAX_ITERATIONS 20

byte iter = 0;
bit done = 0;

/* ---------------------------------
 * Reset all reusable global state
 * --------------------------------- */
inline reset_sem_mgr_state() {
    int i;

    /* Reset semaphores */
    i = 0;
    do
    :: i < MAX_MODEL_SEMAS ->
        model_semaphores[i].isInitialised = false;
        model_semaphores[i].isFlushed = false;
        model_semaphores[i].Count = 0;
        model_semaphores[i].task_queue_count = 0;
        i++
    :: else -> break
    od

    /* Reset tasks */
    i = 1;
    do
    :: i < TASK_MAX ->
        tasks[i].state = Ready;
        tasks[i].tout = false;
        tasks[i].ticks = 0;
        i++
    :: else -> break
    od
}

/* ---------------------------------
 * Bounded iteration controller
 * --------------------------------- */
proctype IterationController() {
    do
    :: iter < MAX_ITERATIONS ->
         iter++
    :: else ->
         done = 1;
         break
    od
}

/* ---------------------------------
 * Entry point
 * --------------------------------- */
init {

    run System();
    run Clock();
    run IterationController();

    do
    :: done -> break

    :: else ->
        atomic {
            reset_sem_mgr_state();
            chooseScenario();
        }

        /* Spawn fresh task set */
        run Runner(task1Core, TASK1_ID, task_in[TASK1_ID]);
        run Worker0(task2Core, TASK2_ID, task_in[TASK2_ID]);
        run Worker1(task3Core, TASK3_ID, task_in[TASK3_ID]);

        /* Wait until all tasks finish */
        do
        :: (tasks[TASK1_ID].state == Zombie &&
            tasks[TASK2_ID].state == Zombie &&
            tasks[TASK3_ID].state == Zombie) -> break
        :: else -> skip
        od
    od

#ifdef TEST_GEN
    assert(false);   /* force trail generation */
#endif
}

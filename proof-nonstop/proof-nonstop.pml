/* SPDX-License-Identifier: BSD-2-Clause */

/*
 * proof-nonstop.pml
 *
 * Copyright (C) 2019-2021 Trinity College Dublin (www.tcd.ie)
 *
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *
 *     * Redistributions in binary form must reproduce the above
 *       copyright notice, this list of conditions and the following
 *       disclaimer in the documentation and/or other materials provided
 *       with the distribution.
 *
 *     * Neither the name of the copyright holders nor the names of its
 *       contributors may be used to endorse or promote products derived
 *       from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

 /*
 * Proof-of-concept "non-stop" model:
 * Simple Runner/Worker handshake with finite trace window
 *
 *     * Both tasks (runner/worker) execute forever (non-stop behaviour)
 *     * A bounded "trace window" limits exploration to MAX_STEPS
 *
 * This is intentionally generic to prove the concpet before mapping onto
 * RTEMS models.
 */

#define MAX_STEPS 50

byte steps = 0;
bit done = 0;

/* Channels emulate event/semaphore signal */
chan req = [0] of {bit};
chan ack = [0] of {bit};

byte outstanding = 0; /* 0 / 1: only allow one outstanding request for simplicity */

/* Bounded trace window: once MAX_STEPS reached, everyone stops */
proctype traceWindow()
{
    do
    :: (steps < MAX_STEPS) ->
        steps++
    :: else ->
        done = 1;
        break
    od
}

/* Runner task: periodically sends a request (if none outstanding) and waits for ack */
proctype Runner()
{
    byte id = 1;
    do
    :: done -> break
    :: (outstanding == 0) ->
            outstanding = 1; /* can cause fault and obtain traces by setting > 1 */

            assert(outstanding <= 1); /* Safety property check */

            req!id;
            ack?id;
            outstanding = 0
    od
}

/* Worker task: repeatedly wait for a signal, performs a small action, acks. */
proctype Worker()
{
    byte id;
    do
    :: done -> break
    :: req?id ->
        /* action */
        ack!id
    od
}

init
{
    atomic{
        run traceWindow();
        run Runner();
        run Worker();
    }
}
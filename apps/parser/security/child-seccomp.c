/* Compile the fixed amd64 fixture profile to classic BPF for Bubblewrap. */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/sched.h>
#include <seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <unistd.h>

int main(void)
{
    if (seccomp_arch_native() != SCMP_ARCH_X86_64) {
        return 1;
    }
    scmp_filter_ctx filter = seccomp_init(SCMP_ACT_ERRNO(EOPNOTSUPP));
    if (filter == NULL) {
        return 1;
    }
    /* Only the fixed Python child, local reads and writes, and the fork witness. */
    const int calls[] = {
        SCMP_SYS(access), SCMP_SYS(arch_prctl), SCMP_SYS(brk), SCMP_SYS(close),
        SCMP_SYS(execve), SCMP_SYS(exit), SCMP_SYS(exit_group), SCMP_SYS(fcntl),
        SCMP_SYS(fork), SCMP_SYS(fstat), SCMP_SYS(futex), SCMP_SYS(getcwd),
        SCMP_SYS(getdents64), SCMP_SYS(getegid), SCMP_SYS(geteuid), SCMP_SYS(getgid),
        SCMP_SYS(getpid), SCMP_SYS(getppid), SCMP_SYS(getrandom), SCMP_SYS(gettid),
        SCMP_SYS(getuid), SCMP_SYS(ioctl), SCMP_SYS(lseek), SCMP_SYS(madvise),
        SCMP_SYS(mmap), SCMP_SYS(mprotect), SCMP_SYS(mremap), SCMP_SYS(munmap),
        SCMP_SYS(newfstatat), SCMP_SYS(openat), SCMP_SYS(pipe2), SCMP_SYS(pread64), SCMP_SYS(prlimit64),
        SCMP_SYS(read), SCMP_SYS(readlink), SCMP_SYS(readlinkat), SCMP_SYS(rseq),
        SCMP_SYS(rt_sigaction), SCMP_SYS(rt_sigprocmask), SCMP_SYS(rt_sigreturn),
        SCMP_SYS(set_robust_list), SCMP_SYS(set_tid_address), SCMP_SYS(setsid),
        SCMP_SYS(wait4), SCMP_SYS(write),
    };
    for (size_t number = 0; number < sizeof(calls) / sizeof(calls[0]); number++) {
        if (seccomp_rule_add(filter, SCMP_ACT_ALLOW, calls[number], 0) < 0) {
            seccomp_release(filter);
            return 1;
        }
    }
    const uint64_t namespace_flags =
        CLONE_NEWNS | CLONE_NEWUSER | CLONE_NEWPID | CLONE_NEWIPC | CLONE_NEWNET |
        CLONE_NEWUTS | CLONE_NEWCGROUP | CLONE_NEWTIME;
    int status = seccomp_rule_add(filter, SCMP_ACT_ALLOW, SCMP_SYS(clone), 1,
                                  SCMP_A0(SCMP_CMP_MASKED_EQ, namespace_flags, 0));
    if (status == 0) {
        status = seccomp_export_bpf(filter, STDOUT_FILENO);
    }
    seccomp_release(filter);
    return status == 0 ? 0 : 1;
}

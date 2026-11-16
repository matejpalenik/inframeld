# Qualification candidate for the fixed Ubuntu 24.04 x64 primitive.
abi <abi/4.0>,
@{probe_readonly} = /newroot/{usr/local/,usr/lib/x86_64-linux-gnu/,lib64/ld-linux-x86-64.so.2,fixture/test_sandbox_boundaries.py}

profile inframeld-parser-probe flags=(mediate_deleted) {
  # Docker drops all capabilities. The setup privileges below apply after
  # entering Bubblewrap's private user namespace.
  userns create,
  capability sys_admin,
  capability setuid,
  capability setgid,
  capability net_admin,
  capability setpcap,
  capability sys_ptrace,

  / mr,
  /usr/local/** mr,
  /usr/local/bin/python{,3,3.13} ix,
  /opt/probe-tools/bwrap rmix,
  /usr/lib/x86_64-linux-gnu/** mr,
  /lib{,64}/** mr,
  /etc/ld.so.cache r,
  /etc/{group,passwd,nsswitch.conf,hosts,resolv.conf,localtime} r,
  /probe/** r,
  /fixture/test_sandbox_boundaries.py r,
  /proc/ r,
  owner /proc/ w,
  /proc/{self,thread-self}/** r,
  owner /proc/[0-9]*/** r,
  owner /proc/[0-9]*/{uid_map,gid_map,setgroups} w,
  /proc/[0-9]*/{status,stat,task/[0-9]*/children} r,
  /proc/{meminfo,stat,cpuinfo,sys/kernel/osrelease} r,
  /proc/sys/kernel/overflow{uid,gid} r,
  /dev/null rw,
  /dev/urandom r,
  owner /tmp/** rwk,
  owner /newroot/** rwk,
  owner /scratch/** rwk,
  signal (receive,send) peer=inframeld-parser-probe,
  signal (receive) peer=unconfined,
  ptrace (read,readby) peer=inframeld-parser-probe,
  network unix,
  # Bubblewrap uses NETLINK_ROUTE for loopback only after creating its network namespace.
  # The inner seccomp filter denies socket creation, including netlink.
  network netlink raw,

  # Namespace setup mount operations and the fixed private fixture bindings.
  mount options=(rslave,silent) -> /,
  mount fstype=tmpfs -> /tmp/,
  mount options=(rbind) /tmp/newroot/ -> /tmp/newroot/,
  pivot_root oldroot=/tmp/oldroot/ /tmp/,
  mount options=(rbind) /oldroot/proc/ -> /proc/,
  mount fstype=tmpfs -> /newroot/scratch/,
  # The setup descriptor reaches mountinfo through the old root during remounts.
  owner /oldroot/proc/[0-9]*/mountinfo r,
  /oldroot/usr/local/ r,
  /oldroot/usr/lib/x86_64-linux-gnu/ r,
  /oldroot/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 r,
  /oldroot/probe/tests/test_sandbox_boundaries.py r,
  /oldroot/dev/null r,
  mount options=(rbind) /oldroot/usr/local/ -> /newroot/usr/local/,
  mount options=(rbind) /oldroot/usr/lib/x86_64-linux-gnu/ -> /newroot/usr/lib/x86_64-linux-gnu/,
  mount options=(rbind) /oldroot/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 -> /newroot/lib64/ld-linux-x86-64.so.2,
  mount options=(rbind) /oldroot/probe/tests/test_sandbox_boundaries.py -> /newroot/fixture/test_sandbox_boundaries.py,
  mount options=(rbind) /oldroot/dev/null -> /newroot/dev/null,
  # ENOSYS selects Bubblewrap's legacy remount, which adds nosuid, nodev and ro.
  mount options=(remount,bind,ro,nosuid,nodev,silent) -> @{probe_readonly},
  mount options=(remount,bind,ro,nosuid,nodev,relatime,silent) -> @{probe_readonly},
  mount options=(rprivate,silent) -> /oldroot/,
  umount /oldroot/,
  pivot_root oldroot=/newroot/ /newroot/,
  # The last detach is the former root reached by the saved directory descriptor.
  umount /,
}

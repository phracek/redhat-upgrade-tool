#!/bin/bash
# upgrade-prep.sh - set up upgrade dir for upgrading
#
# Copyright (C) 2012 Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Will Woods <wwoods@redhat.com>

die() { echo "$@"; exit 1; }

. /run/initramfs/upgrade.conf || die "can't find /run/initramfs/upgrade.conf"
[ -n "$UPGRADEROOT" ] || die "UPGRADEROOT is not set"
[ -d "$UPGRADEROOT" ] || die "$UPGRADEROOT does not exist"

grep -qw 'upgrade.test' /proc/cmdline && UPGRADETEST=1 || UPGRADETEST=''

# remove our boot entry
[ $UPGRADETEST ] || new-kernel-pkg --remove redhat-upgrade-tool

# make target dir for systemd's pivot_root
mkdir -p $UPGRADEROOT/mnt

# unmount any temporary mounts set up by the initramfs
cat /proc/mounts | while read dev mnt rest; do
    [ -f $mnt/.please-unmount ] && umount -l $mnt
done

# XXX backwards compatibility for F17->F18, drop for F18->F19
# if /lib/modules/$(uname -r) is a mount, umount it
moddir=$(readlink -eq /lib/modules/$(uname -r))
grep -qw $moddir /proc/mounts && umount -l $moddir

echo "moving mounts into $UPGRADEROOT"
mount --make-unbindable $UPGRADEROOT
# bind everything into the upgrade chroot
mount --rbind / $UPGRADEROOT/sysroot || die "couldn't bind / into upgrade dir"
# make the bind mounts separate from the original mounts
mount --make-rprivate /
# unmount the original mounts, i.e.:
#   anything that's a block device, not root, and not under UPGRADEROOT
tac /proc/mounts | while read dev mnt type opts x y; do
    if [ -b "$dev" -a "$mnt" != "/" -a "${mnt#$UPGRADEROOT}" == "$mnt" ]; then
        umount $mnt && echo "moved $mnt" || echo "failed to move $mnt"
    fi
done

# XXX: we can drop this once there's a way to pass args to new init
echo "switching upgraderoot default target to upgrade.target"
# switch the upgrade chroot target to upgrade.target
ln -sf upgrade.target $UPGRADEROOT/etc/systemd/system/default.target
rm -f $UPGRADEROOT/usr/lib/systemd/system/default.target

echo "upgrade prep complete, switching root..."

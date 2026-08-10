#!/usr/bin/env bash
# Configura e crea la VM Bliss OS in VirtualBox per l'analisi del traffico.
# La VM sara' in bridge mode (stessa rete della lavatrice 192.168.1.235).

set -e
VBOX="/c/Program Files/Oracle/VirtualBox"
VM_NAME="BlissOS-Candy"
ISO="C:/AndroidSdk/bliss-os.iso"
VMDK="C:/AndroidSdk/BlissOS-Candy.vdi"

echo "=== Creazione VM Bliss OS in VirtualBox ==="

# Elimina VM esistente se presente
"$VBOX/VBoxManage" unregistervm "$VM_NAME" --delete 2>/dev/null || true

# Crea la VM
"$VBOX/VBoxManage" createvm --name "$VM_NAME" --ostype "Linux26_64" --register

# CPU e RAM
"$VBOX/VBoxManage" modifyvm "$VM_NAME" \
    --cpus 2 \
    --memory 4096 \
    --vram 128 \
    --graphicscontroller vmsvga \
    --ioapic on \
    --acpi on

# Disco
if [ ! -f "$VMDK" ]; then
    echo "Creazione disco VDI da 16GB..."
    "$VBox/VBoxManage" createmedium disk --filename "$VMDK" --size 16384
fi

# Controller SATA + disco
"$VBox/VBoxManage" storagectl "$VM_NAME" --name "SATA" --add sata --controller IntelAhci
"$VBox/VBoxManage" storageattach "$VM_NAME" --storagectl "SATA" --port 0 --device 0 \
    --type hdd --medium "$VMDK"

# Controller IDE + ISO (per il boot iniziale)
"$VBox/VBoxManage" storagectl "$VM_NAME" --name "IDE" --add ide --controller PIIX4
"$VBOX/VBoxManage" storageattach "$VM_NAME" --storagectl "IDE" --port 1 --device 0 \
    --type dvddrive --medium "$ISO"

# Rete in BRIDGE (cosi' la VM vede la lavatrice a 192.168.1.235)
"$VBOX/VBoxManage" modifyvm "$VM_NAME" \
    --nic1 bridged \
    --bridgeadapter1 "$( "$VBOX/VBoxManage" list bridgedifs | grep -m1 '^Name:' | sed 's/^Name:[[:space:]]*//' )"

# Audio off (dà problemi su Android-x86)
"$VBOX/VBoxManage" modifyvm "$VM_NAME" --audio none

# USB off
"$VBOX/VBoxManage" modifyvm "$VM_NAME" --usb off

# Boot da DVD (per installare)
"$VBOX/VBoxManage" modifyvm "$VM_NAME" --boot1 dvd --boot2 disk --boot3 none --boot4 none

echo ""
echo "=== VM creata! ==="
"$VBOX/VBoxManage" showvminfo "$VM_NAME" | grep -E "Name:|OS|Memory|CPUs|NIC|Storage" | head -10
echo ""
echo "Per avviare:"
echo "  \"\$VBOX/VBoxManage\" startvm \"$VM_NAME\" --type gui"

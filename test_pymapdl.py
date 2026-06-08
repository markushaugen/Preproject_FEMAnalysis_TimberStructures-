from ansys.mapdl.core import launch_mapdl

# Launch ANSYS
mapdl = launch_mapdl()
mapdl.prep7()

# Beam
mapdl.block(0, 1000, 0, 200, 0, 140)
vid_beam = mapdl.geometry.vnum[-1]
print(f"Beam volume: {vid_beam}")

# Slot
mapdl.block(679, 1001, -1, 201, 65, 75)
vid_slot = mapdl.geometry.vnum[-1]
print(f"Slot volume: {vid_slot}")

# Boolean subtract
mapdl.vsbv(vid_beam, vid_slot)
vid_beam = mapdl.geometry.vnum[-1]
print(f"Beam after subtract: {vid_beam}")

mapdl.exit()

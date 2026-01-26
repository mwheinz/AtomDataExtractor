# Potensic Atom 2 FC 2 file definition for
# the HexFiend editor.
while {![end]} {
		section "Record" {
				uint32 "recordId";			# 4
				uint8   "c1";				# 5
				uint64 "timeStamp";			# 13
				uint32 -hex "s1s2";			# 17
				uint16 "flightCounter";		# 19
				bytes 26 "unknown1";		# 45
				uint8 "gpsLock?";			# 46
				uint8 "satellites";			# 47
				int32 "droneLat";			# 51
				int32 "droneLon";			# 55
				bytes 242 "unknown2";		# 297
				uint8 -hex "m1State";		# 298
				byte "unknown3"
				uint8 -hex "m2State";		# 300
				byte "unknown4"
				uint8 -hex "m3State";		# 302
				byte "unknown5"
				uint8 -hex "m4State";		# 304
				bytes 24 "unknown6"; 		# 328
				float "altitude";			# 332
				bytes 44 "unknown7";        # 376
				float "heading";            # 380
				bytes 36 "unknown8";		# 416
				float "distanceHome"; 		# 420
				int32 "homeLat";			# 424
				int32 "homeLon";			# 428
				bytes 5 "unknown9";			# 433
				uint8 -hex "flightMode";    # 434
				bytes 6 "unknown10";		# 440
				int16 "batteryV1";			# 442
				int16 "batteryV2";			# 444
				int16 "batteryA";			# 446
				int8  "batteryT";           # 447
				bytes 4 "unknown11";		# 451
				int8  "battery%";			# 452
				bytes 60 "data";			# 512
		}
}


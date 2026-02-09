enum GPSLock: u8 {
    No,
    GPSL1,
    GPSL2,
    Yes
};
enum FlightMode: u8 {
    Video=7,
    Normal,
    Sport
};

enum DroneMode: u8 {
    Off,
    IdleLaunch,
    Flying,
    Landing
};

enum PositioningMode: u8 {
    Attitude=1,
    Optical,
    GPS
};

struct fc2Record {
    // 0    starts at zero and increments.
    u32     recordId;

    // 4    Always zero?
    u8      u1;

    // 5    Elapsed time in MS.
    u64     elapsed;

    // 13   Initially zero, then goes non-zero shortly after the fc2 log begins.
    //      Observed values include 0x1e, 0x1e001e, 0x780078, 0x190019, 0x280028, 
    u8      u2[4];

    // 17   The # of times the drone has flown? Sometimes increments in a single fc2 file? 
    u16     flightCount;

    // 19   Lots of frequently changing data.
    u8      b3[26];

    // 45   Goes from 0 to 3 when the lat/lon is correct? No other values observed.
    GPSLock gpsLock;

    // 46   The number of satellites the drone sees?
    u8 satellites;

    // 47   The latitude and longitude of the drone. Not valid till gpsLock==3.
    s32 droneLat;
    s32 dronLon;

    u8 b4[241];
    u8 m1[2];
    u8 m2[2];
    u8 m3[2];
    u8 m4[2];
    u8 b5[24];
    float altitude;
    u8 b6[44];
    float heading;
    u8 b7[28];
    float wind; 
    u8 b8[4];
    float dhome;
    s32 hlat;
    s32 hlon;
    u8 b9[5];
    FlightMode flightmode;
    u8 b10[6];
    s16 batteryv1;
    s16 batteryv2;
    s16 batteryma;
    s8 btemp;
    u8 b11[4];
    u8 batterypct;
    u8 b12[4];
    DroneMode dronemode;
    PositioningMode posmode;
    u8 data[54];
};

fc2Record record[10000] @ 0x0;

#pragma loop_limit 16384
#include <std/mem.pat>
#include <std/io.pat>
#include <std/core.pat>
#include <std/math.pat>

fn checkZeros(ref auto arr) {
    bool allZero = true;
    for (u32 i = 0, i < std::core::member_count(arr), i = i + 1) {
        if (arr[i] != 0) {
            allZero = false;
            break;
        }
    }
    return allZero;
};

fn hexBytes(ref auto bytes) {
    str bstr="";
    for (u32 i = 0, i < std::core::member_count(bytes), i=i+1) {
        bstr=bstr+std::format("{:02X}:", bytes[i]);
    }
    return bstr;
};

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
    // 0    record id starts at zero and increments.
    u32     recordId;

    // 4    Always zero?
    u8      z4;

    // 5    Elapsed time in MS.
    u64     elapsed;

    // 13   Initially zero, occasionally changes to one of a few distinct values.
    //      Observed values include 0, 25, 30, 35, 40, and 120.
    u16     u13;
    
    // 15   Zero or, if u13 is non-zero, will equal u13.
    u16     u15;
    
    // 17   The # of times the drone has flown? Sometimes increments in a single fc2 file? 
    u16     flightCount;

    // 19   Lots of frequently changing data.
    u8      b3[26];

    // 45   Goes from 0 to 3 when the lat/lon is correct? No other values observed.
    GPSLock gpsLock;

    // 46   The number of satellites the drone sees?
    u8      satellites;

    // 47   The latitude and longitude of the drone. Not valid till gpsLock==3.
    s32     droneLat;
    s32     dronLon;
    
    // 55   goes non-zero when the # of satellites > 0. Some kind of signal strength?
    s32     u55;
    
    // 57   Unknown. Initially either 0 or 1, then varies between 0 and 1.
    float   u57;
    // 63   Unknown. Initially 5, then varies between 0 and 5.
    float   u63;
    // 67   Unknown. Initially 10, then varies between 0 and 10.
    float   u67;
    
    u8      b71[225];
    
    // 296  m*[1] appears to enumerate the state of a motor.
    //      m*[0] seems to be related but the meaning is unknown.
    u8      m1[2];
    u8      m2[2];
    u8      m3[2];
    u8      m4[2];
    
    // 304  Unknown.
    u8      b304[24];
    
    // 328  Drone alitude above ground, in meters.
    float   altitude;
    
    // 332  Unknown.
    u8      b332[44];
    
    // 376  Drone heading, in radians.
    float   heading;
    
    // 380  Unknown.
    u8      b380[28];
    
    // 408  wind direction, in radians.
    float   wind; 
    
    // 412  Unknown.
    float   u412;
    
    //      Distance to home, in meters.
    float   dhome;
    
    
    s32     hlat;
    s32     hlon;
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

fc2Record record[std::mem::size() / sizeof(fc2Record)] @ 0x0;

// Make sure the record length is correct...
std::print("Record Size: {}\n\n", sizeof(fc2Record));

/*

u32 mu=0;
u32 rid = -1;

std::print("Record dump:\n");
for (u32 i = 0, i < std::mem::size() / 512, i = i + 1) {
    std::print("{}\t{:.2f}\t{:.2f}",
        record[i].recordId, 
        record[i].altitude,
        record[i].u412
    );
    if (record[i].u412 > mu) {
        mu = record[i].u412;
        rid = i;
    }
}
std::print("Max u412: {}, record = {}", mu, rid);
*/

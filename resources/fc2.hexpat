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
    //      May be related to the Flight Mode - goes non-zero at the same time
    //      the initial flight mode goes from video to normal. May change again during flight.
    //      Observed values include 0, 25, 30, 35, 40, and 120.
    u16     u13;
    
    // 15   Zero or, if u13 is non-zero, will equal u13.
    u16     u15;
    
    // 17   The number of times the drone has flown. Imcrements with each landing.
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
    s32     gpsQuality;
    
    // 59   Appears to represent the confidence in the drone's position, with
    //      0.0 being the best and 1.0 being the worst.
    float   posConfidence1;

    // 63   Initially 5, then varies between 0 and 5. Possibly related
    //      to the accuracy of the drone's position with 5.0 being poor
    //      and 0.0 being best.
    float   horizontalConfidence;
    // 67   Initially 10, then varies between 0 and 10. Possibly related
    //      to the accuracy of the drone's position with 10.0 being poor
    //      and 0.0 being best.
    float   verticalConfidence;
    
    u8      b71[225];
    
    // 296  m*[1] appears to enumerate the state of a motor.
    //      m*[0] seems to be related but the meaning is unknown.
    u8      m1[2];
    u8      m2[2];
    u8      m3[2];
    u8      m4[2];
    
    // 304  Distance from the home point in meters.
    //      posX is probably the position east or west of home.
    //      posY is probably the position north or south of home.
    float   posX; 
    float   posY;

    // 312  Possibly information on the drone's orientation.
    float   pitch;
    float   roll;
    float   pitchRate;
    float   rollRate;
    
    // 328  Drone alitude above take off point, in meters.
    float   altitude;
    
    // 332  Unknown.
    u8      b332[44];
    
    // 376  Drone heading, in radians.
    float   heading;
    
    // 380  Components of velocity?
    float   deltaX;
    float   deltaY;
    float   deltaZ;

    // 392  Ground speed?
    float   f392;
    
    // 396  Sometimes goes non-zero during flight, but not always. Returns to
    //      zero after landing.
    float   f396;

    // 400  Appears to be a constant value. Always equals "5050.0"
    float   f400;

    // 404  Sometimes goes non-zero during flight, but not always. Returns to
    //      zero after landing. Correlated with altitude?
    float   f404;
    
    // 408  wind direction, in radians.
    float   wind; 
    
    // 412  Appears to represent how hard the drone motors are working.
    float   thrust;
    
    // 416  Distance to home, in meters.
    float   dhome;
    
    // 420  Lat and lon of the home point, in degrees * 1e7.
    s32     hlat;
    s32     hlon;

    // 428  Unknown.
    u8      b428;

    // 429  Non-zero when return-to-home is activated.
    u8      rth;

    // 430  Unknown.
    u8      b430[3];

    // 433  Current flight mode. 7 = low performance ("video"), 8 = normal performance, 9 = high performance ("sport")
    FlightMode flightmode;

    // 434  Unknown.
    u8      b434[6];

    // 440  Battery information. batteryv1, batteryv2 are the voltages output 
    //      by the battery cells. batteryma is the current output by the
    //      battery. btemp is the temperature of the battery.
    //      batterypct is the charge level of the battery.
    s16     batteryv1;
    s16     batteryv2;
    s16     batteryma;
    s8      btemp;

    // 447  Unknown.
    u8      b447[4];

    // 451  Battery charge level.
    u8      batterypct;

    // 452  Unknown.
    u8      b452[4];

    // 456  The drone operating mode. 0 = motors off, 1 = idle/launching, 
    //      2 = flying, 3 = landing.
    DroneMode dronemode;

    // 457  The drone positioning mode. 1=attitude, 2=optical, 3=GPS.
    PositioningMode posmode;

    // 458  Unknown.
    u8      b458[54];
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

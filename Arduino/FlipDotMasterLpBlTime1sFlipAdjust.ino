  // Code Written for FlipDotMasterB
  // Includes
  #include "LowPower.h" // https://github.com/rocketscream/Low-Power
  #include <Wire.h>     // Arduino Library
  #include "RTClib.h"   // https://github.com/adafruit/RTClib
  
  // RTC Library Call
  RTC_DS1307 rtc;
  char daysOfTheWeek[7][12] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};

  // Button Define (hrs/mins)
  int bHrs = 3;
  int bMins = 4;

  // Button State
  int bHrsState = 0;
  int bMinsState = 0;
  
  // Sprinf Buffer for Time Formatting
  char buffer[64]="";

  // Add a Variable to colData 1234 -> 4321
  byte flipLR[4] = {3,2,1,0};
  
  // Variable Declares
  //int led = 13;
  boolean ledState = false;
  int supply=7;
  
  // Sleep Counter Declare
  int sleepCounter = 8; 
  
  // Define Shift Register Pins 
  int latchPin = 10 ; 
  int clockPin = 13; 
  int dataPin  = 11; 
  
   // Set Locations of Fets relative to Shift Registers Outputs
  byte supBits[4]  = {0,3,6,9};
  byte setBits[4]  = {1,4,7,10};
  byte resBits[4]  = {2,5,8,11};
  
  // Data Variable for Display
  byte dotState = 0;
  
  // Create a Variable to Store Intended State of Col
  byte colData[4] = {0,0,0,0};
  
  // Create a Variable to Store Old State of Col
  byte oldData[4] = {255,255,255,255};
  
  // Data Variable Holds Column Display State
  // Accounts for the need for 3 bits per dot
  // Unsigned Long has 32 bits (4 bytes) 
  // MSB 7 6 5 4 3 2 1 LSB
  unsigned long regData[4] = {0,0,0,0};

  // Init Display Data
  byte initData[4] = {1,2,4,8};
  byte xData[4]    = {9,6,6,9};
  byte oData[4]    = {15,9,9,15};
  byte oneData[4]  = {15,15,15,15};
  byte zeroData[4] = {0,0,0,0};
  int initDelay   = 250;
//******************************************************************************
// Begin Setup Routine
//*****************************************************************************
void setup()
{
  delay(1000);
   
  // Hardware Setup
  Serial.begin(9600);       
  pinMode(supply, OUTPUT);
  digitalWrite(supply, LOW);

  // Button Setup
  pinMode(bHrs, INPUT);
  pinMode(bMins,INPUT);

  // Hello World
  Serial.println();
  Serial.println("I am your FlipDot Binary Clock");

  // RTC Setup
  if (! rtc.begin()) {
    Serial.println("Couldn't find RTC");
    while (1);
  }  

  // Get Current Date
  DateTime now = rtc.now();
  sprintf(buffer, "Current Time %02d/%02d/%02d %02d:%02d:%02d",now.year(),now.month(),now.day(), now.hour(),now.minute(),now.second());   
  Serial.println(buffer);

  // Get Compiled Date
  DateTime compiled = DateTime(__DATE__, __TIME__);

  // Assemble a Formatted Time Buffer - For Serial Output
  sprintf(buffer, "Compiled Time %02d/%02d/%02d %02d:%02d:%02d",compiled.year(),compiled.month(),compiled.day(), compiled.hour(),compiled.minute(),compiled.second());   
  Serial.println(buffer); 

  // Set RTC to Compiled Time 
  if (now.unixtime() < compiled.unixtime()) {
  Serial.println("RTC is older than compile time! Updating");
  // following line sets the RTC to the date & time this sketch was compiled
  rtc.adjust(DateTime(__DATE__, __TIME__));
  }

  // FlipDot Shift Register Pins
  pinMode(latchPin, OUTPUT);
  pinMode(clockPin, OUTPUT);
  pinMode(dataPin, OUTPUT);

  // 24V Power Supply On
  setSupply(1);
  
  // Run Initial Display Pattern
  Serial.println("Running Demo Pattern");
  patternDisplay();
  
  // 24V Power Supply Off
  setSupply(0);

  // Set the Time
  displayTime(); 
}

//******************************************************************************
// Main Loop
//******************************************************************************
void loop() 
{
  //******************************************************************************
  // Wakeup Loop
  //******************************************************************************

    // Check for Hr Button Pressed
    if ( digitalRead(bHrs) == LOW){
      Serial.println("Hour Button Pressed"); 
      setHrs();
    }
  
    // Check for Min Button Pressed
    if ( digitalRead(bMins) == LOW){
      Serial.println("Minute Button Pressed"); 
      setMins();  
    }
  
    if (sleepCounter > 9) {
      //Increment Sleep Counter
      sleepCounter--;
      
      //Blink Led for 5 ms as HeartBeat
      blinkLed(5);
    }
    else {
      // We are within 9 seconds of Minute Change
      displayTime(); 
    }

  //******************************************************************************
  // GoTo Sleep
  //******************************************************************************
  
  // Enter power down state for Xs with ADC and BOD module disabled
  LowPower.powerDown(SLEEP_1S, ADC_OFF, BOD_OFF);  
}
//******************************************************************************
void setHrs() {
  uint8_t newHrs = 0;
  DateTime now = rtc.now();
  
  //Increment Hour Value
  newHrs = now.hour()+1;
  
  // Handle Hour overflow
  if (newHrs > 23) newHrs = 0;

  // Set New Time
  rtc.adjust(DateTime(now.year(), now.month(), now.day(),newHrs, now.minute(), now.second()));

  // Display New Time
  displayTime();
}
//******************************************************************************
void setMins() {
  uint8_t newMins = 0;
  DateTime now = rtc.now();
  
  //Increment Minute Value
  newMins = now.minute()+1;
  
  // Handle Hour overflow
  if (newMins > 59) newMins = 0;

  // Set New Time - Seconds to Zero as well
  rtc.adjust(DateTime(now.year(), now.month(), now.day(),now.hour(), newMins, 0));

  // Display New Time
  displayTime();
}
//******************************************************************************
void displayTime() {
  // Get the Date
  DateTime now = rtc.now();
  
  // Assemble a Formatted Time Buffer - For Serial Output
  sprintf(buffer, "%02d/%02d/%02d %02d:%02d:%02d",now.year(),now.month(),now.day(), now.hour(),now.minute(),now.second());   
  Serial.println(buffer); 
  
  // Assemble a Formatted Time Buffer - For Serial Output
  //sprintf(buffer, "%02d:%02d:%02d", now.hour(),now.minute(),now.second());   
  //Serial.println(buffer); 

  //Assemble a Formatted Time Buffer - For Binary Output
  sprintf(buffer, "%02d%02d", now.hour(),now.minute());  
  for(int i = 0; i<4; i++) {
    colData[flipLR[i]]=buffer[i];
  }

  // Set the FlipDot Display with the Time
  setSupply(1);
  setData();
  setSupply(0);

  // Calculate time to Sleep
  sleepCounter = 60 - now.second();
}
//******************************************************************************
void blinkLed(byte blinkDelay) {
  digitalWrite(clockPin, HIGH);
  delay(blinkDelay);
  digitalWrite(clockPin, LOW);
}
//******************************************************************************
void setSupply(byte supplyState){

  if (supplyState == 0){
    digitalWrite(supply, LOW);
  }
  else {
    digitalWrite(supply, HIGH);
  }
}
//******************************************************************************
void patternDisplay() {
  
  blankDisplay(); 
  
  // Display All 1's
  for(int i = 0; i<4; i++) {
    colData[i]=oneData[i];
  }
  setData();
  blankDisplay(); 
  
  // Display All X's
  for(int i = 0; i<4; i++) {
    colData[i]=xData[i];
  }
  setData();
  blankDisplay(); 
  
  // Display All O's
  for(int i = 0; i<4; i++) {
    colData[i]=oData[i];
  }
  setData();
  blankDisplay();    
}
//******************************************************************************
void blankDisplay() {
  delay(500);
  // Display All 0's
  for(int i = 0; i<4; i++) {
    colData[i]=zeroData[i];
  } 
  setData();
  delay(500);
}
//******************************************************************************
void initDisplay() {
  Serial.print("Init Delay = ");
  Serial.print(initDelay,DEC);
  Serial.print("\n");
  for(int i = 0; i<4; i++) {
    for(int j = 0; j<4; j++) {
      colData[i]=initData[j];
      setData();
      delay(initDelay);

      colData[i]=0;
      setData();
      delay(initDelay);
    }
  }
}
//******************************************************************************
void setData() {
  // Take XOR of colData and oldData
  // So that only dots that have changed are updated
  byte xorData[5] = {0,0,0,0,0};

  for(int i = 0; i<4; i++) {
    xorData[i]=colData[i] ^ oldData[i];
  /*Serial.print("colData ");
    Serial.print(colData[i]);
    Serial.print(" ");
    
    Serial.print(" colData ");
    Serial.print(colData[i], BIN);
    Serial.print(" ");
  
    Serial.print("oldData ");
    Serial.print(oldData[i]);
    Serial.print(" ");
    
    Serial.print(" oldData ");
    Serial.print(oldData[i], BIN);
    Serial.print(" ");
  
    Serial.print("xorData ");
    Serial.print(xorData[i]);
    Serial.print(" ");
    
    Serial.print(" xorData ");
    Serial.print(xorData[i], BIN);
    Serial.print(" ");
    Serial.println("");
  */
    // Set/Reset the Col Dots
    for (byte j=0; j < 4; j++){
      // Clear Register Data
      regData[i]=0;
      
      // Dot XOR Bit Test Result
      byte xorIdx=bitRead(xorData[i],j);
      //Serial.print(" xorIdx ");
      //Serial.print(xorIdx);
      
      // Dot Value to Write
      byte dotIdx=bitRead(colData[i],j);
      //Serial.print(" dotIdx ");
      //Serial.print(dotIdx);
      //Serial.println(); 

      //xorIdx = 1;
      // Does Dot need to Flip? 0 = No; 1 = Yes
      if (xorIdx==0){
        bitWrite(regData[i],supBits[j],0);
        bitWrite(regData[i],setBits[j],0);
        bitWrite(regData[i],resBits[j],0);
      }
      else { // Dot Needs to Flip
        bitWrite(regData[i],supBits[j],1);
    
      // Change Set/Res Pins as Needed
      // Dot = O or White
        if (dotIdx==0){
          bitWrite(regData[i],setBits[j],0);
          bitWrite(regData[i],resBits[j],1);
        }
        // Dot = 1 or Black
        else {
          bitWrite(regData[i],setBits[j],1);
          bitWrite(regData[i],resBits[j],0);
        }
      }
      // Shift Dot Data Out
      shiftData();
      // Clear Register Data
      regData[i]=0;
    }
    // Set colData = oldData
    oldData[i] = colData[i];
  }
}
//******************************************************************************
void shiftData(){
  for(int j = 0; j<4; j++) {
    /*Serial.print("data ");
    Serial.print(colData[j]);
    Serial.print(" Int ");
    Serial.print(regData[j]);  
    Serial.print(" BIN ");
    Serial.println(regData[j], BIN); 
    */
    shiftOut(dataPin, clockPin, MSBFIRST, regData[j] >> 8); //Send the data
    shiftOut(dataPin, clockPin, MSBFIRST, regData[j]); //Send the data
  }
  
  digitalWrite(latchPin, HIGH); //Pull latch HIGH to send data
  delayMicroseconds(10);
  digitalWrite(latchPin, LOW); // Pull latch LOW to stop sending data
  delayMicroseconds(650);

  for(int j = 0; j<4; j++) {
    shiftOut(dataPin, clockPin, MSBFIRST, 0); //Send the data
    shiftOut(dataPin, clockPin, MSBFIRST, 0); //Send the data
  }

  digitalWrite(latchPin, HIGH); //Pull latch HIGH to send data
  delayMicroseconds(10);
  digitalWrite(latchPin, LOW); // Pull latch LOW to stop sending data
}

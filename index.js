AWS.config.apiVersions = {
  s3: "2006-03-01",
  // other service API versions
};

var creds = new AWS.Credentials({
  accessKeyId: "your-KEYID",
  secretAccessKey: "your-KEY",
});

var s3 = new AWS.S3({
  credentials: creds,
  region: "your-region",
});

var iterator = 1;
let data;
let imageArray;
let metaData;
let s3Data;
let urlObject;
let url;

//audio for sound alert
var snd = new Audio("Alarm1.mp3");
//to mark the number of frames in which there are people without ppe
let Index = 0;

let slideshow = document.getElementById("slideshow");
let output = document.getElementById("output");
let dangerIndex = document.getElementById("dangerIndex");

function infinite_run() {
  var params = {
    Bucket: "your-bucket-name",
    Key: "your-key",
  };

  let myPromise1 = s3.getObject(params).promise();

  myPromise1
    .then(
      function (fromResolve) {
        iterator = iterator + 1;
        data = fromResolve;
        metaData = data.Metadata;
        imageArray = data.Body;
        console.log(data);
        console.log(metaData);
        console.log(imageArray);
        //   document.write(metaData);
        //   output.innerHTML = metaData.toString();
        // output.innerHTML = JSON.stringify(metaData);
        // metaData = fromResolve.Metadata;
        // imageArray = fromResolve.Body;
        let PPE = metaData.numberofppes;
        let Person = metaData.numberofpersons;
        output.innerHTML =
          "Number of Persons: " + Person + " and Number of PPEs: " + PPE;
        if (Person > PPE) {
          Index = Index + 1;
          if (Index >= 3) {
            dangerIndex.innerHTML = "Danger Index is now " + Index;
            console.log("send sound alert!");
            // document.getElementById("alarm").play();
            snd.play();
            alert("Dangerous!");
            //send alert using other aws service
          }
        } else {
          Index = 0;
          dangerIndex.innerHTML = "Danger Index is now " + Index;
        }
        //this method returns a url as a promise object, from the 'getObject' method
        let getUrl = s3.getSignedUrlPromise("getObject", params);
        getUrl.then(
          function (url) {
            console.log("The url is ", url);
            slideshow.src = url;
          },
          function (err) {
            console.log(err);
          }
        );
      },
      // when a new object in not present in s3, display the previous one
      function () {
        metaData = data.Metadata;
        imageArray = data.Body;
        console.log(data);
        console.log(metaData);
        console.log(imageArray);

        let PPE = metaData.numberofppes;
        let Person = metaData.numberofpersons;
        output.innerHTML =
          "Number of Persons: " + Person + " and Number of PPEs: " + PPE;
        if (Person > PPE) {
          Index = Index + 1;
          if (Index >= 5) {
            dangerIndex.innerHTML = "Danger Index is now " + Index;
            console.log("send sound alert!");
            // document.getElementById("alarm").play();
            snd.play();
            alert("Dangerous!");
            //send real alert
          }
        } else {
          Index = 0;
          dangerIndex.innerHTML = "Danger Index is now " + Index;
        }
      }
    )
    .catch(function (fromReject) {
      console.log(fromReject);
    });
}

//run it every 5s
infinite_run();
setInterval(infinite_run, 5000);

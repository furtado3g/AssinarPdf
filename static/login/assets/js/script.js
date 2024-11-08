function handleWithLoginButtonClicked(event) {
  event.preventDefault();
  var username = document.getElementById("username").value;
  var password = document.getElementById("password").value;
  if (username === "" || password === "") {
    alert("Please fill in all fields");
    return;
  }
  const formData = new FormData(document.getElementById("loginForm"));
  fetch("http://127.0.0.1:5000/login", {
    method: "POST",
    body: formData
  })
    .then(response => response.json())
    .then(({token} )=> {
      console.log(token);
      localStorage.setItem("token", token);
      if (data.error) {
        alert(data.error);
      } else {
        window.location
          .replace("http://127.0.0.1:5000/file_upload")
          .then(window.location.reload());
      }
    })
    .catch(err => {
      console.log(err);
    });
}
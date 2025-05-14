import React from 'react'
import './Navbar.css'

const Navbar = () => {
  return (
    // <nav>
    //     <div className='Company_Name'>Athenyx</div>
        // <ul>
        //     <li><a href='#'>Home</a></li>
        //     {/* <li><a href='#'>Home</a></li> */}
        //     <li><a href='#'>Services</a></li>
        //     <li><a href='#'>About</a></li>
        //     <li><a href='#'>Contact</a></li>
        // </ul>
    // </nav>
    <>
 <nav class="navbar navbar-expand-lg navbar-light fixed-top bg-light">
  <div class="container-fluid">
  <div className='Company_Name'>Athenyx</div>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarSupportedContent" aria-controls="navbarSupportedContent" aria-expanded="false" aria-label="Toggle navigation">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarSupportedContent">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">    

      </ul>
      <div class="d-flex">
          <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
            <li><a href='#hero'>Home</a></li>
            <li><a href='#services'>Services</a></li>
            <li><a href='#about'>About</a></li>
            <li><a href='#footer'>Contact</a></li>
        </ul>
      </div>
    </div>
  </div>
</nav>
    </>
  )
}

export default Navbar
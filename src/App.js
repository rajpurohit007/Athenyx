import React from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import Services from './components/Services';
import Footer from './components/Footer';
import About from './components/About';


const App = () => {
  return (
    <>
    <Navbar />
  
    <Hero />


    <Services />

    <About />

    <Footer />
    </>
  )
}

export default App